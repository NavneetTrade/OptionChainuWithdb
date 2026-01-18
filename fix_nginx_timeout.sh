#!/bin/bash
# Fix nginx timeout for 504 Gateway Timeout errors

echo "🔧 Fixing nginx timeout configuration..."

# Backup current config
sudo cp /etc/nginx/sites-available/option-chain /etc/nginx/sites-available/option-chain.backup.$(date +%Y%m%d_%H%M%S)

# Update nginx config with increased timeouts
sudo tee /etc/nginx/sites-available/option-chain > /dev/null << 'EOF'
server {
    listen 80;
    server_name _;

    # Increase buffer sizes
    client_max_body_size 100M;
    client_body_buffer_size 128k;
    
    # Main Next.js Dashboard (Modern UI)
    location / {
        proxy_pass http://localhost:3000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_cache_bypass $http_upgrade;
        
        # Increase timeouts
        proxy_connect_timeout 300s;
        proxy_send_timeout 300s;
        proxy_read_timeout 300s;
        send_timeout 300s;
    }

    # Streamlit Dashboard
    location /streamlit {
        proxy_pass http://localhost:8501;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_buffering off;
        
        # Increase timeouts for Streamlit
        proxy_connect_timeout 600s;
        proxy_send_timeout 600s;
        proxy_read_timeout 600s;
        send_timeout 600s;
    }

    # FastAPI Backend
    location /api {
        proxy_pass http://localhost:8000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        
        # Increase timeouts for API
        proxy_connect_timeout 300s;
        proxy_send_timeout 300s;
        proxy_read_timeout 300s;
        send_timeout 300s;
    }

    # WebSocket endpoint
    location /ws {
        proxy_pass http://localhost:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        
        # WebSocket timeouts
        proxy_connect_timeout 7d;
        proxy_send_timeout 7d;
        proxy_read_timeout 7d;
    }
}
EOF

# Test nginx config
sudo nginx -t

if [ $? -eq 0 ]; then
    echo "✅ Nginx config is valid"
    sudo systemctl reload nginx
    echo "✅ Nginx reloaded with new timeout settings"
else
    echo "❌ Nginx config has errors, restoring backup..."
    sudo cp /etc/nginx/sites-available/option-chain.backup.* /etc/nginx/sites-available/option-chain
    sudo nginx -t
fi

echo ""
echo "✅ Done! Timeouts increased to 300-600 seconds"
