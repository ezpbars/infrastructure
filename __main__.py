from typing import List
import pulumi
import vpc
import tls
from key import Key
import webapp
import rqlite
import redis
import reverse_proxy

config = pulumi.Config()
github_username = config.require("github_username")
github_pat = config.require_secret("github_pat")
domain = config.require("domain")
rqlite_id_offset = config.get_int("rqlite_id_offset")
if rqlite_id_offset is None:
    rqlite_id_offset = 0

key = Key("key", "key.pub", "key.openssh")

main_vpc = vpc.VirtualPrivateCloud("main_vpc", key)
main_rqlite = rqlite.RqliteCluster("main_rqlite", main_vpc, id_offset=rqlite_id_offset)
main_redis = redis.RedisCluster("main_redis", main_vpc)


def make_standard_webapp_configuration(args) -> str:
    rqlite_ips: List[str] = args[: len(main_rqlite.instances)]
    redis_ips: List[str] = args[len(rqlite_ips) :]

    joined_rqlite_ips = ",".join(rqlite_ips)
    joined_redis_ips = ",".join(redis_ips)

    return "\n".join(
        [
            f'export RQLITE_IPS="{joined_rqlite_ips}"',
            f'export REDIS_IPS="{joined_redis_ips}"',
        ]
    )


standard_configuration = pulumi.Output.all(
    *[instance.private_ip for instance in main_rqlite.instances],
    *[instance.private_ip for instance in main_redis.instances],
).apply(make_standard_webapp_configuration)

backend_rest = webapp.Webapp(
    "backend_rest",
    main_vpc,
    "ezpbars/backend",
    github_username,
    github_pat,
    main_vpc.bastion.public_ip,
    key,
    configuration=standard_configuration,
)
backend_ws = webapp.Webapp(
    "backend_ws",
    main_vpc,
    "ezpbars/websocket",
    github_username,
    github_pat,
    main_vpc.bastion.public_ip,
    key,
    configuration=standard_configuration,
)
frontend = webapp.Webapp(
    "frontend",
    main_vpc,
    "ezpbars/frontend",
    github_username,
    github_pat,
    main_vpc.bastion.public_ip,
    key,
    configuration=standard_configuration,
)
main_reverse_proxy = reverse_proxy.ReverseProxy(
    "main_reverse_proxy", main_vpc, key, backend_rest, backend_ws, frontend
)
tls = tls.TransportLayerSecurity(
    "tls",
    domain,
    main_vpc.vpc.id,
    [subnet.id for subnet in main_vpc.public_subnets],
    [instance.id for instance in main_reverse_proxy.reverse_proxies],
)
