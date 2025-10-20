# Hướng dẫn cấu hình Database

## Vấn đề đã sửa

Lỗi `TimeoutError` khi kết nối PostgreSQL trong Docker đã được khắc phục với các cải tiến:

### 1. **Retry Logic với Exponential Backoff**
- Tự động thử lại kết nối tối đa 5 lần
- Chờ 2 giây giữa các lần thử
- Logging chi tiết để debug

### 2. **Connection Pool Configuration**
```python
await asyncpg.create_pool(
    dsn=settings.DATABASE_URL,
    min_size=2,           # Minimum connections
    max_size=10,          # Maximum connections
    command_timeout=60,   # Command execution timeout
    timeout=30,           # Connection timeout
)
```

### 3. **Cấu hình DATABASE_URL đúng cho Docker**

#### ❌ SAI (kết nối ra ngoài):
```
DATABASE_URL=postgresql://postgres:123456a%40@103.75.184.164:5432/order_sync_db_dev
```

#### ✅ ĐÚNG (kết nối trong Docker network):
```
DATABASE_URL=postgresql://etsyuser:etS_yP@ss@postgres:5432/etsybot
```

**Lưu ý quan trọng:**
- Sử dụng tên service `postgres` (từ docker-compose.yml) thay vì `localhost` hoặc IP
- Username, password, database name phải khớp với docker-compose.yml

## Cách sử dụng

### Development (Local)
```env
DATABASE_URL=postgresql://etsyuser:etS_yP@ss@localhost:5432/etsybot
```

### Production (Docker)
```env
DATABASE_URL=postgresql://etsyuser:etS_yP@ss@postgres:5432/etsybot
```

## Kiểm tra kết nối

### Từ trong container:
```bash
docker exec -it etsy-bot python3 -c "
import asyncio
from src.db.postgres import init_pg_pool

async def test():
    pool = await init_pg_pool()
    print('✅ Kết nối thành công!')
    await pool.close()

asyncio.run(test())
"
```

### Xem logs:
```bash
docker logs etsy-bot
docker logs etsy-poller
```

## Troubleshooting

### Lỗi: `TimeoutError`
**Nguyên nhân:** Database chưa sẵn sàng hoặc cấu hình sai
**Giải pháp:**
1. Kiểm tra `DATABASE_URL` trong `.env`
2. Đợi database khởi động hoàn toàn: `docker logs esty-postgres`
3. Verify health check: `docker ps` (phải thấy `healthy`)

### Lỗi: `could not translate host name "postgres" to address`
**Nguyên nhân:** Container không trong cùng Docker network
**Giải pháp:** Đảm bảo `depends_on` được cấu hình đúng trong docker-compose.yml

### Lỗi: `authentication failed`
**Nguyên nhân:** Username/password không khớp
**Giải pháp:** Kiểm tra lại credentials trong `.env` và `docker-compose.yml`

## Best Practices

1. **Không hardcode credentials** - Luôn dùng environment variables
2. **Sử dụng health checks** - Đợi services sẵn sàng trước khi start
3. **Implement retry logic** - Handle transient failures
4. **Proper connection pooling** - Tối ưu performance và resource usage
5. **Logging** - Monitor connection status

## Environment Variables Required

```env
BOT_TOKEN=<telegram_bot_token>
DATABASE_URL=postgresql://<user>:<password>@<host>:<port>/<database>
REDIS_URL=redis://<host>:<port>/<db>
API_KEY=<your_api_key>
```
