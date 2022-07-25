#!/usr/bin/env bash
bash shared/wait_boot_finished.sh
cp config.sh /home/ec2-user/config.sh
cp repo.sh /home/ec2-user/repo.sh
cp update_webapp.sh /home/ec2-user/update_webapp.sh
cd /usr/local/src
. /home/ec2-user/repo.sh
mkdir webapp
cd webapp
git init
git remote add origin "https://${GITHUB_USERNAME}:${GITHUB_PAT}@github.com/${GITHUB_REPOSITORY}"
git pull origin main
cd /home/ec2-user
bash -c "source /home/ec2-user/config.sh && bash scripts/auto/after_install.sh && bash scripts/auto/start.sh"
cd /home/ec2-user
crontab -l > cron
echo "@reboot sudo bash /usr/local/src/webapp/scripts/auto/start.sh" >> cron
crontab cron
rm cron
