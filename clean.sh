#!/usr/bin/env bash 

source ./config

rm ./rootfs/root/aws_* || true
rm ./rootfs/root/.config  || true
rm ./rootfs/root/.credentials || true
rm -rf ./rootfs/root/.cache || true
rm ./rootfs/root/.bash_history || true
rm ./rootfs/www/.bash_history || true
rm ./rootfs/apps/rds_slow_query_log_examiner/www/*.data || true
rm ./rootfs/apps/rds_slow_query_log_examiner/www/*.pyc || true
rm -rf ./rootfs/apps/rds_slow_query_log_examiner/www/report_*/ || true
