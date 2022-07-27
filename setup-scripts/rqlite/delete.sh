#!/usr/bin/env bash
stop_rqlite() {
    while screen -S rqlited -X stuff "^C"
    do
        sleep 1
    done
}

deprovision_rqlite() {
    source config.sh
    if [ -z "$DEPROVISION_IP" ]
    then
        echo "warning: not deprovisioning because no deprovision ip provided"
        return
    fi

    echo "deprovisioning using $DEPROVISION_IP"
    curl -XDELETE "http://$DEPROVISION_IP:4001/remove" -d "{\"id\": \"$NODE_ID\"}"
}

uninstall_rqlite() {
    if [ -f /home/ec2-user/rqlite_uninstall.txt ]
    then
        while read p
        do
            rm -rf "$p"
        done < /home/ec2-user/rqlite_uninstall.txt
        rm /home/ec2-user/rqlite_uninstall.txt
    fi
    
    crontab -l > cron
    sed -i '/^@reboot sudo screen -dmS rqlited/d' cron
    crontab cron
    rm cron
}

stop_rqlite
deprovision_rqlite
uninstall_rqlite
