module.exports = {
  apps: [
    {
      name: 'visa-scheduler',
      script: 'visa.py',
      interpreter: 'python3',
      // Restart interval controlled by WORK_LIMIT_TIME in config.ini (not cron)
      // Script exits after work limit, PM2 autorestart creates relative intervals
      // This avoids fixed-time restarts and ensures restarts happen relative to script start
      max_memory_restart: '500M',    // Restart if memory exceeds 500MB
      error_file: './logs/pm2-error.log',
      out_file: './logs/pm2-out.log',
      log_date_format: 'YYYY-MM-DD HH:mm:ss',
      autorestart: true,             // Auto-restart on crash or normal exit
      max_restarts: 10,              // Max 10 restarts in min_uptime window
      min_uptime: '60s'              // Must run 60s to count as successful start
    }
  ]
};
