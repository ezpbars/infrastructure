import pulumi
import vpc
import tls
from key import Key
import webapp
import rqlite
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
main_rqlite = rqlite.RqliteCluster(
    "main_rqlite",
    main_vpc,
    id_offset=rqlite_id_offset
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
