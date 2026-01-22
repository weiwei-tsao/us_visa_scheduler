module.exports = {
  apps: [
    {
      name: 'visa-scheduler',
      script: 'run_visa.sh',
      interpreter: 'bash',
      max_memory_restart: '500M',
      error_file: './logs/pm2-error.log',
      out_file: './logs/pm2-out.log',
      log_date_format: 'YYYY-MM-DD HH:mm:ss',
      autorestart: true,
      max_restarts: 10,
      min_uptime: '60s'
    }
  ]
};
