#! POWERSHELL

Remove-Item ./rootfs/www/.bash_history -ErrorAction SilentlyContinue
Remove-Item ./rootfs/apps/rds_slow_query_log_examiner/www/*.data -ErrorAction SilentlyContinue
Remove-Item ./rootfs/apps/rds_slow_query_log_examiner/www/*.data.* -ErrorAction SilentlyContinue
Remove-Item ./rootfs/apps/rds_slow_query_log_examiner/www/report_*/ -Recurse -Force -ErrorAction SilentlyContinue

