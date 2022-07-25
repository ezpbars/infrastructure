wait_internet() {
    while ! curl google.com >> /dev/null
    do
        sleep 5
    done
}

install_basic_dependencies() {
    yum update -y
    echo "exclude=python3" >> /etc/yum.conf

    amazon-linux-extras enable epel=stable
    yum clean metadata
    rpm --rebuilddb
    yum install -y epel-release git jq
    yum update -y
}

verify_iam_profile() {
    curl http://169.254.169.254/latest/meta-data/iam/info | jq -e .InstanceProfileId
    return $?
}

wait_iam_profile() {
    local ctr="0"
    while ! verify_iam_profile
    do
        ctr=$(($ctr + 1))
        echo "initialization failed to verify iam profile (ctr=$ctr)" >> /home/ec2-user/boot_warnings
        sleep 30

        if (($ctr > 5))
        then
            break
        fi
    done
}

wait_internet
install_basic_dependencies
wait_iam_profile
