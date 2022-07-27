"""This module allows creating a rqlite cluster"""
from typing import List
from remote_executor import RemoteExecution, RemoteExecutionInputs
from vpc import VirtualPrivateCloud
import pulumi_aws as aws
import pulumi


class RqliteCluster:
    """Describes a rqlite cluster with one server on each subnet"""

    def __init__(
        self, resource_name: str, vpc: VirtualPrivateCloud, id_offset: int = 0
    ) -> None:
        """Creates a new rqlite cluster running on the private subnets
        of the given virtual private cloud.

        Args:
            resource_name (str): the resource name prefix to use for resources
                created by this instance
            vpc (VirtualPrivateCloud): the virtual private cloud to construct
                the rqlite cluster within
            id_offset (int): the number of rqlite servers which were once part
                of this cluster and should no longer be. for example, if you want
                to cleanly update the cluster seamlessly, increase the id_offset by
                1 and pulumi up until you have replaced every server
        """
        self.resource_name: str = resource_name
        """the resource name prefix to use for resources created by this instance"""

        self.vpc: VirtualPrivateCloud = vpc
        """the virtual private cloud the cluster is within"""

        self.security_group: aws.ec2.SecurityGroup = aws.ec2.SecurityGroup(
            f"{resource_name}-security-group",
            description="allows incoming 4001-4002 tcp (rqlite) + ssh from bastion",
            vpc_id=self.vpc.vpc.id,
            ingress=[
                aws.ec2.SecurityGroupIngressArgs(
                    from_port=4001,
                    to_port=4002,
                    protocol="tcp",
                    cidr_blocks=["0.0.0.0/0"],
                ),
                aws.ec2.SecurityGroupIngressArgs(
                    from_port=22,
                    to_port=22,
                    protocol="tcp",
                    cidr_blocks=[
                        self.vpc.bastion.private_ip.apply(lambda ip: f"{ip}/32")
                    ],
                ),
            ],
            egress=[
                aws.ec2.SecurityGroupEgressArgs(
                    from_port=0, to_port=0, protocol="-1", cidr_blocks=["0.0.0.0/0"]
                )
            ],
            tags={"Name": f"{resource_name} rqlite"},
        )

        self.instance_cluster_ids = list(
            range(id_offset + 1, id_offset + 1 + len(self.vpc.private_subnets))
        )
        """The cluster id for each instance, with index-correspondance to instances"""

        self.instances: List[aws.ec2.Instance] = [
            aws.ec2.Instance(
                f"{resource_name}-instance-{cluster_id}",
                ami=self.vpc.amazon_linux_bleeding_arm64.id,
                associate_public_ip_address=False,
                instance_type="t4g.nano",
                subnet_id=self.vpc.private_subnets[
                    cluster_id % len(self.vpc.private_subnets)
                ],
                key_name=self.vpc.key.key_pair.key_name,
                vpc_security_group_ids=[self.security_group.id],
                iam_instance_profile=self.vpc.standard_instance_profile.name,
                root_block_device=aws.ec2.InstanceRootBlockDeviceArgs(
                    iops=3000, throughput=125, volume_size=8, volume_type="gp3"
                ),
                tags={
                    "Name": f"{resource_name} {vpc.availability_zones[cluster_id % len(self.vpc.private_subnets)]} [{cluster_id}]"
                },
            )
            for cluster_id in self.instance_cluster_ids
        ]
        """the instances within this cluster. note that they are not necessarily in the
        same order as the private subnets of the vpc, since we ensure that a cluster_id
        which is 1, remainder the number of subnets, is at subnets[1] - even if the cluster
        id offset is not a multiple of the number of private subnets in the vpc -- this allows
        the desired "increment cluster id offset by 1 to swap 1 instance out" behavior
        """

        self.remote_executions: List[RemoteExecution] = [
            RemoteExecution(
                f"{resource_name}-remote-execution-{cluster_id}",
                props=RemoteExecutionInputs(
                    script_name="setup-scripts/rqlite",
                    file_substitutions=pulumi.Output.all(
                        *[i.private_ip for i in self.instances], cluster_id
                    ).apply(
                        lambda args: {  # careful - you can't access cluster_id in here reliably
                            "config.sh": {
                                "NODE_ID": str(args[-1]),
                                "MY_IP": args[
                                    self.instance_cluster_ids.index(args[-1])
                                ],
                                "JOIN_ADDRESS": ",".join(
                                    f"http://{ip}:4001"
                                    for idx, ip in enumerate(args[:-1])
                                    if self.instance_cluster_ids[idx] != args[-1]
                                ),
                                "DEPROVISION_IP": args[
                                    (self.instance_cluster_ids.index(args[-1]) + 1)
                                    % len(self.instances)
                                ],
                            }
                        }
                    ),
                    host=instance.private_ip,
                    private_key=self.vpc.key.private_key_path,
                    bastion=self.vpc.bastion.public_ip,
                    shared_script_name="setup-scripts/shared",
                ),
            )
            for cluster_id, instance in zip(
                self.instance_cluster_ids,
                self.instances,
            )
        ]
        """the remote executions required to bootstrap and maintain the cluster, in the
        same order as instances (which is not necessarily the same order as the subnets
        the instances are in)
        """
