# shubot

shubot 重构计划。

## 开始运行

1. 建立环境 & 安装依赖

   ```shell
   python3 -m venv .venv
   . .venv/bin/activate
   pip install -r requirements.txt
   ```

2. 激活环境

   ```shell
   . .venv/bin/activate
   ```

3. 升级数据库 (TODO: 使用 migration 框架处理数据库版本升级)

   ```shell
   python db.py
   ```

4. 拷贝配置文件并修改

   ```shell
   cp -n config.example.yaml config.yaml
   ${EDITOR:-vi} config.yaml
   ```

5. 运行

   ```shell
   python -m shubot
   # 或指定配置文件
   python -m shubot -c config.yaml
   ```

## 本地开发

可以直接使用 `docker compose up` 启动需要的外部依赖，如 `mariadb` 数据库。

## 数据库问题

- `users.last_checkin` 列不存在。

```sql
ALTER TABLE shubot.users ADD last_checkin DATE NULL;
```

## TODO

- [ ] 使用 migration 框架处理数据库版本升级
- [ ] 安装 Webhook 处理事件而非 polling 服务器获取更好性能
