DROP PROCEDURE IF EXISTS shubot_rob_user;
CREATE PROCEDURE shubot_rob_user(IN p_uid INT, IN p_cooldown INT, IN p_daily_max INT)
    -- 打劫用户
    -- p_uid: 打劫人 ID
    -- p_cooldown: 冷却时间 (秒)
    -- p_daily_max: 每日打劫上限
BEGIN
    DECLARE rob_count INT DEFAULT 0;
    DECLARE rob_date DATETIME DEFAULT NULL;
    DECLARE rob_found INT DEFAULT 0;

    DECLARE EXIT HANDLER FOR SQLEXCEPTION BEGIN
        ROLLBACK;
        -- 返回 0 代表发生了异常
        SELECT 0, 0;
    END;

    START TRANSACTION;
    SELECT 1,
           rr.count,
           rr.last_rob
    INTO
        rob_found, rob_count, rob_date
    from rob_records rr
    where rr.user_id = p_uid
    limit 1;

    IF rob_found = 0 THEN
        -- 未曾打劫过，成功。
        INSERT INTO rob_records
            (user_id, count, last_rob)
        VALUES (p_uid, 1, NOW());
        SELECT 1, 1;
    ELSEIF DATE(rob_date) != CURRENT_DATE THEN
        -- 今日未打劫，成功。
        UPDATE rob_records
        SET count    = 1,
            last_rob = NOW()
        WHERE user_id = p_uid;
        SELECT 2, 1;
    ELSEIF rob_count >= p_daily_max THEN
        -- 次数达到了上限
        SELECT -1, 0;
    ELSEIF TIMESTAMPDIFF(SECOND, rob_date, NOW()) <= p_cooldown THEN
        -- 未冷却
        SELECT -2, 0;
    ELSE
        -- 打劫一次，成功。
        UPDATE rob_records as rr
        SET count    = rob_count + 1,
            last_rob = NOW()
        WHERE rr.user_id = p_uid;
        SELECT 3, rob_count + 1;
    END IF;
    COMMIT;
END;

DROP PROCEDURE IF EXISTS shubot_rob_get_user_pts;
CREATE PROCEDURE shubot_rob_get_user_pts(IN p_uid INT, OUT pts INT)
    -- 获取用户的积分
    -- p_uid: 用户ID
BEGIN
    DECLARE found INT DEFAULT 0;

    SELECT 1, u.points
    INTO found, pts
    from users u
    where u.user_id = p_uid
    limit 1;

    IF found = 0 THEN
        -- 目标不存在，建立用户。
        INSERT INTO users (user_id, points)
        VALUES (p_uid, 0);

        SET pts = 0;
    END IF;
END;

DROP PROCEDURE IF EXISTS shubot_rob_transfer;
CREATE PROCEDURE shubot_rob_transfer(IN p_victim_uid INT, IN p_robber_uid INT, IN p_rob_ratio FLOAT)
    -- 打劫用户
    -- p_victim_uid: 被盗用户
    -- p_robber_uid: 抢劫用户
    -- p_rob_ratio: 转账比例
BEGIN
    DECLARE victim_pts INT DEFAULT 0;
    DECLARE robber_pts INT DEFAULT 0;
    DECLARE rob_pts INT DEFAULT 0;
    DECLARE status INT DEFAULT 1;

    DECLARE EXIT HANDLER FOR SQLEXCEPTION BEGIN
        ROLLBACK;
        -- 返回 0 代表发生了异常
        SELECT 0, 0, 0, 0;
    END;

    START TRANSACTION;

    CALL shubot_rob_get_user_pts(p_victim_uid, victim_pts);
    CALL shubot_rob_get_user_pts(p_robber_uid, robber_pts);

    SET rob_pts = FLOOR(p_rob_ratio * victim_pts);

    if victim_pts = 0 THEN
        -- 输家没钱
        SET status = -1;
    ELSEIF rob_pts = 0 THEN
        -- 比例太低，值太低了
        SET status = -2;
    ELSE
        -- 成功，开始转账
        set victim_pts = victim_pts - rob_pts;
        set robber_pts = robber_pts + rob_pts;

        UPDATE users
        SET points = victim_pts
        WHERE user_id = p_victim_uid;

        UPDATE users
        SET points = robber_pts
        WHERE user_id = p_robber_uid;
    END IF;

    SELECT status, rob_pts, victim_pts, robber_pts;
    COMMIT;
END;

DROP PROCEDURE IF EXISTS shubot_rob_reset_user;
CREATE PROCEDURE shubot_rob_reset_user(IN p_victim_uid INT)
    -- 打劫用户
    -- p_victim_uid: 被盗用户
    -- p_robber_uid: 抢劫用户
    -- p_rob_ratio: 转账比例
BEGIN
    DECLARE EXIT HANDLER FOR SQLEXCEPTION BEGIN
        ROLLBACK;
        SELECT 0;
    END;

    START TRANSACTION;

    -- 没钱了
    UPDATE users
    SET points = 0
    WHERE user_id = p_victim_uid;

    -- 修为归零 (下次访问自动生成白板号)
    DELETE
    FROM user_cultivation
    WHERE user_id = p_victim_uid;

    SELECT 1;
    COMMIT;
END;
