module.exports = {
  apps: [
    {
      name: 'visa-scheduler',
      script: 'run_visa.sh',
      interpreter: 'bash',
      max_memory_restart: '500M',

      // ===========================================
      // LOG RESPONSIBILITIES:
      // - PM2 manages: pm2-out.log, pm2-error.log (stdout/stderr)
      // - Python manages: visa_scheduler.json.log, visa_scheduler.error.log
      // Each system handles its own rotation independently.
      // ===========================================

      // PM2 log configuration (stdout/stderr only)
      error_file: './logs/pm2-error.log',
      out_file: './logs/pm2-out.log',
      log_date_format: 'YYYY-MM-DD HH:mm:ss',

      // PM2 log rotation (requires pm2-logrotate module)
      // Install: pm2 install pm2-logrotate
      // Configure:
      //   pm2 set pm2-logrotate:max_size 10M
      //   pm2 set pm2-logrotate:retain 7
      //   pm2 set pm2-logrotate:compress true
      //   pm2 set pm2-logrotate:dateFormat YYYY-MM-DD
      //   pm2 set pm2-logrotate:rotateModule true

      // Keep stdout/stderr separate for quick error filtering
      combine_logs: false,

      autorestart: true,
      max_restarts: 10,
      min_uptime: '60s',

      // Environment variables
      env: {
        NODE_ENV: 'production'
      }
    }
  ]
};
