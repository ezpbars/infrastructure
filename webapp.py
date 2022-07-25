"""Describes a basic stateless application which is downloaded from
a github repository and then can install itself after invoking the
scripts/auto/after_install.sh from the repository, and the application
is run via the scripts/auto/start.sh
"""
from typing import List
import pulumi_aws as aws
from vpc import VirtualPrivateCloud
from key import Key
from remote_executor import RemoteExecution, RemoteExecutionInputs


class Webapp:
    """A stateless application downloaded from a github repository and installed via
    calling scripts/auto/after_install.sh in the repository. The application should
    be startable via scripts/auto/start.sh and stoppable via scripts/auto/stop.sh.
    The update flow is scripts/auto/stop.sh, scripts/auto/before_install.sh,
    git pull, scripts/auto/after_install.sh, scripts/auto/start.sh
    """

    def __init__(
        self,
        resource_name: str,
        vpc: VirtualPrivateCloud,
        github_repository: str,
        github_username: str,
        github_pat: str,
        bastion: str,
        key: Key,
        architecture: str = "arm64",
        instance_type: str = "t4g.nano",
        num_subnets: int = 2,
        num_instances_per_subnet: int = 1,
        configuration: str = "",
    ):
        """Creates a new webapp in the first N private subnets of the
        given virtual private cloud.

        The application is installed from the given github repository url (specified
        via the https url) and authorization is done through the given github personal
        access token.

        Args:
            resource_name (str): The prefix to use for resource names for resources generated
                by this instance
            vpc (VirtualPrivateCloud): the virtual private cloud to install the application
                on
            github_repository (str): the repository containing the application, e.g., foobar/project
            github_username (str): the github username to use when connecting with github
            github_pat (str): the github personal access token to use to connect to the
                repository
            bastion (str): The public ip address of the server to proxy the ssh
                requests through, since the instances are in a private subnet
            key (Key): the key to configure the instances to be reachable from
            architecture (str): the architecture to use for the application
            instance_type (str): the instance type to use for the application
            num_subnets (int): how many subnets to install the application to
            num_instances_per_subnet (int): how many instances of the application to
                install in each subnet
            configuration (str): The shell code to install under "environment.sh"
                for the webapp under the home directory, which is executed
                prior to installing/running the application. Typically this is
                a series of export commands containing environment variables for
                the application, such as the ip addresses of database servers
        """
        self.resource_name: str = resource_name
        """The prefix to use for resource names for resources generated by this instance"""

        self.vpc: VirtualPrivateCloud = vpc
        """The virtual private cloud the application is installed in"""

        self.github_repository: str = github_repository
        """The github repository containing the applications source, e.g., foobar/project"""

        self.github_username: str = github_username
        """The github username to use when accessing the repository"""

        self.github_pat: str = github_pat
        """The github personal access token to us to access the repository"""

        self.bastion: str = bastion
        """The public ip address of the bastion the instances can be reached through"""

        self.key: aws.ec2.KeyPair = key
        """The key that the instances were setup to accept connections from"""

        self.architecture: str = architecture
        """The architecture to use for the instances"""

        self.instance_type: str = instance_type
        """The type of instances to use for the application"""

        self.num_subnets: int = num_subnets
        """How many subnets to install the application in"""

        self.num_instances_per_subnet = num_instances_per_subnet
        """How many instances of the application to install in each subnet"""

        self.configuration: str = configuration
        """The configuration for the application as shell code"""

        self.ami: aws.ec2.Ami = aws.ec2.get_ami(
            most_recent=True,
            filters=[
                aws.ec2.GetAmiFilterArgs(name="name", values=["amzn2-ami-*"]),
                aws.ec2.GetAmiFilterArgs(name="virtualization-type", values=["hvm"]),
                aws.ec2.GetAmiFilterArgs(name="architecture", values=[architecture]),
            ],
            owners=["137112412989"],
        )
        """The amazon machine id that the instances use"""

        self.security_group: aws.ec2.SecurityGroup = aws.ec2.SecurityGroup(
            f"{resource_name}-security-group",
            description="Allow all traffic",
            egress=[aws.ec2.SecurityGroupEgressArgs(
                from_port=0,
                protocol="-1",
                to_port=0,
                cidr_blocks=['0.0.0.0/0']
            )],
            ingress=[aws.ec2.SecurityGroupIngressArgs(
                from_port=0,
                protocol=-1,
                to_port=0,
                cidr_blocks=["0.0.0.0/0"]
            )],
            tags={"Name": f"{resource_name} security group"}
        )
        """the security group used for instances"""

        self.instances_by_subnet: List[List[aws.ec2.Instance]] = [
            [
                aws.ec2.Instance(
                    f"{resource_name}-instance-{subnet_idx}-{instance_idx}",
                    ami=self.ami.id,
                    associate_public_ip_address=False,
                    instance_type=instance_type,
                    subnet_id=subnet.id,
                    vpc_security_group_ids=[self.security_group.id],
                    tags={
                        "Name": f"{resource_name} {vpc.availability_zones[subnet_idx]}-{instance_idx}"
                    },
                )
                for instance_idx in range(len(num_instances_per_subnet))
            ]
            for subnet_idx, subnet in enumerate(vpc.private_subnets[:num_subnets])
        ]
        """The ec2 instances running the application, broken down by subnet"""

        self.remote_executions_by_subnet: List[List[RemoteExecution]] = [
            [
                RemoteExecution(
                    f"{resource_name}-re-{subnet_idx}-{instance_idx}",
                    props=RemoteExecutionInputs(
                        script_name="setup-scripts/webapp",
                        file_substitutions={
                            "config.sh": {"CONFIGURATION": configuration},
                            "repo.sh": {
                                "GITHUB_REPOSITORY": github_repository,
                                "GITHUB_USERNAME": github_username,
                                "GITHUB_PAT": github_pat,
                            },
                        },
                        host=instance.private_ip,
                        bastion=bastion,
                        shared_script_name="setup-scripts/shared",
                    ),
                )
                for instance_idx, instance in enumerate(
                    self.instances_by_subnet[subnet_idx]
                )
            ]
            for subnet_idx in range(num_subnets)
        ]
        """The remote executions repsonsible for installing the applications on each instance,
        broken down by subnet"""
