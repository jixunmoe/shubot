import pymysql

DB_CONFIG = {
    'host': 'localhost',
    'user': 'root',
    'password': '',
    'database': 'novel_bot_db'
}

def create_database():
    connection = pymysql.connect(**DB_CONFIG)
    
    try:
        with connection.cursor() as cursor:
            #用户表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    user_id BIGINT NOT NULL UNIQUE,
                    username VARCHAR(255),
                    points INT DEFAULT 0
                )
            """)
            #授权群组表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS authorized_groups (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    group_id BIGINT NOT NULL UNIQUE,
                    group_name VARCHAR(255),
                    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS user_group (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    user_id BIGINT NOT NULL,
                    group_id BIGINT NOT NULL,
                    joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE KEY user_group_unique (user_id, group_id),
                    FOREIGN KEY (user_id) REFERENCES users(user_id)
                )
            """)
            #文件表MD5存储
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS files (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    md5 CHAR(32) NOT NULL UNIQUE,
                    user_id BIGINT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(user_id)
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS gua_records (
                    user_id BIGINT NOT NULL,
                    date DATE NOT NULL,
                    times_used INT DEFAULT 0,
                    PRIMARY KEY (user_id, date),
                    FOREIGN KEY (user_id) REFERENCES users(user_id)
                );
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS user_cultivation (
                    user_id BIGINT PRIMARY KEY,
                    stage INT DEFAULT 0,
                    pills INT DEFAULT 0,
                    next_cost INT DEFAULT 10,
                    FOREIGN KEY (user_id) REFERENCES users(user_id)
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS user_events (
                    user_id BIGINT PRIMARY KEY,
                    last_trigger TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    event_count INT DEFAULT 0,
                    FOREIGN KEY (user_id) REFERENCES users(user_id)
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS rob_records (
                    user_id BIGINT PRIMARY KEY,
                    last_rob TIMESTAMP,
                    count INT DEFAULT 0,
                    FOREIGN KEY (user_id) REFERENCES users(user_id)
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS gang_records (
                    user_id BIGINT PRIMARY KEY,
                    start_date DATE NOT NULL,
                    consecutive_days INT DEFAULT 1,
                    total_donated INT DEFAULT 0,
                    FOREIGN KEY (user_id) REFERENCES users(user_id)
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS slave_records (
                    master_id BIGINT NOT NULL,
                    slave_id BIGINT NOT NULL,
                    group_id BIGINT NOT NULL,
                    created_date DATE NOT NULL,
                    confirmed BOOLEAN DEFAULT FALSE,
                    PRIMARY KEY (master_id, created_date),
                    FOREIGN KEY (master_id) REFERENCES users(user_id),
                    FOREIGN KEY (slave_id) REFERENCES users(user_id)
                )
            """)

        connection.commit()
        print("Database tables created successfully!")
        
    finally:
        connection.close()

if __name__ == "__main__":
    create_database()
