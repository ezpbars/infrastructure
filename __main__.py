from typing import List
import pulumi
import vpc
from tls import TransportLayerSecurity
from key import Key
import webapp
import rqlite
import redis
import reverse_proxy
from cognito import Cognito

config = pulumi.Config()
github_username = config.require("github_username")
github_pat = config.require_secret("github_pat")
domain = config.require("domain")
rqlite_id_offset = config.get_int("rqlite_id_offset")
if rqlite_id_offset is None:
    rqlite_id_offset = 0
deployment_secret = config.require_secret("deployment_secret")
slack_web_errors_url = config.require_secret("slack_web_errors_url")
slack_ops_url = config.require_secret("slack_ops_url")
google_oidc_client_id = config.require("google_oidc_client_id")
google_oidc_client_secret = config.require_secret("google_oidc_client_secret")

key = Key("key", "key.pub", "key.openssh")

main_vpc = vpc.VirtualPrivateCloud("main_vpc", key)
main_rqlite = rqlite.RqliteCluster("main_rqlite", main_vpc, id_offset=rqlite_id_offset)
main_redis = redis.RedisCluster("main_redis", main_vpc)


def make_standard_webapp_configuration(args) -> str:
    rqlite_ips: List[str] = args[: len(main_rqlite.instances)]
    redis_ips: List[str] = args[
        len(rqlite_ips) : len(rqlite_ips) + len(main_redis.instances)
    ]
    remaining = args[len(rqlite_ips) + len(redis_ips) :]
    deploy_secret: str = remaining[0]
    web_errors_url: str = remaining[1]
    ops_url: str = remaining[2]
    login_url: str = remaining[3]
    auth_domain: str = remaining[4]
    auth_client_id: str = remaining[5]
    public_kid_url: str = remaining[6]
    expected_issuer: str = remaining[7]
    domain: str = remaining[8]

    joined_rqlite_ips = ",".join(rqlite_ips)
    joined_redis_ips = ",".join(redis_ips)

    return "\n".join(
        [
            f'export RQLITE_IPS="{joined_rqlite_ips}"',
            f'export REDIS_IPS="{joined_redis_ips}"',
            f'export DEPLOYMENT_SECRET="{deploy_secret}"',
            f'export SLACK_WEB_ERRORS_URL="{web_errors_url}"',
            f'export SLACK_OPS_URL="{ops_url}"',
            f'export LOGIN_URL="{login_url}"',
            f'export AUTH_DOMAIN="{auth_domain}"',
            f'export AUTH_CLIENT_ID="{auth_client_id}"',
            f'export PUBLIC_KID_URL="{public_kid_url}"',
            f'export EXPECTED_ISSUER="{expected_issuer}"',
            f'export ROOT_FRONTEND_URL="https://{domain}"',
            f'export ROOT_BACKEND_URL="https://{domain}"',
            f'export ROOT_WEBSOCKET_URL="wss://{domain}"',
        ]
    )


backend_rest = webapp.Webapp(
    "backend_rest",
    main_vpc,
    "ezpbars/backend",
    github_username,
    github_pat,
    main_vpc.bastion.public_ip,
    key,
)
backend_ws = webapp.Webapp(
    "backend_ws",
    main_vpc,
    "ezpbars/websocket",
    github_username,
    github_pat,
    main_vpc.bastion.public_ip,
    key,
)
frontend = webapp.Webapp(
    "frontend",
    main_vpc,
    "ezpbars/frontend",
    github_username,
    github_pat,
    main_vpc.bastion.public_ip,
    key,
)
jobs = webapp.Webapp(
    "jobs",
    main_vpc,
    "ezpbars/jobs",
    github_username,
    github_pat,
    main_vpc.bastion.public_ip,
    key,
)
itg_tests = webapp.Webapp(
    "itg_tests",
    main_vpc,
    "ezpbars/itg_tests",
    github_username,
    github_pat,
    main_vpc.bastion.public_ip,
    key,
)
main_reverse_proxy = reverse_proxy.ReverseProxy(
    "main_reverse_proxy", main_vpc, key, backend_rest, backend_ws, frontend
)
tls = TransportLayerSecurity(
    "tls",
    domain,
    main_vpc.vpc.id,
    [subnet.id for subnet in main_vpc.public_subnets],
    [instance.id for instance in main_reverse_proxy.reverse_proxies],
)
cognito = Cognito(
    "cognito",
    tls=tls,
    google_oidc_client_id=google_oidc_client_id,
    google_oidc_client_secret=google_oidc_client_secret,
)
standard_configuration = pulumi.Output.all(
    *[instance.private_ip for instance in main_rqlite.instances],
    *[instance.private_ip for instance in main_redis.instances],
    deployment_secret,
    slack_web_errors_url,
    slack_ops_url,
    cognito.token_login_url,
    cognito.auth_domain,
    cognito.user_pool_client.name,
    cognito.public_kid_url,
    cognito.expected_issuer,
    domain,
).apply(make_standard_webapp_configuration)

backend_rest.perform_remote_executions(standard_configuration)
backend_ws.perform_remote_executions(standard_configuration)
frontend.perform_remote_executions(standard_configuration)
jobs.perform_remote_executions(standard_configuration)
itg_tests.perform_remote_executions(standard_configuration)
