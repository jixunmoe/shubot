DROP PROCEDURE IF EXISTS shubot_lottery;
CREATE PROCEDURE shubot_lottery(IN p_uid INT8, IN daily_limit INT, IN cost INT, IN prize INT)
    -- 更新抽奖记录，并更新用户积分
    -- p_uid: 用户ID
    -- daily_limit: 每日抽奖次数限制
    -- cost: 每次抽奖消耗的积分
    -- prize: 抽奖奖品。若是未中奖，传入 0
BEGIN
    DECLARE status INT DEFAULT 0; -- 用户积分
    DECLARE user_pts INT DEFAULT 0; -- 用户积分
    DECLARE user_pts_new INT DEFAULT 0; -- 用户积分
    DECLARE last_lottery DATE DEFAULT NULL; -- 上次抽奖时间
    DECLARE lottery_count INT DEFAULT 0; -- 今日已进行抽奖次数

    DECLARE EXIT HANDLER FOR SQLEXCEPTION BEGIN
        ROLLBACK;
        SELECT 0, 0, 0, 0;
    END;

    START TRANSACTION;

    SELECT u.points, gr.date, gr.times_used
    INTO user_pts, last_lottery, lottery_count
    FROM users u
             LEFT JOIN gua_records gr ON u.user_id = gr.user_id
    WHERE u.user_id = p_uid;

    IF DATE(last_lottery) != UTC_DATE OR last_lottery is NULL OR lottery_count is NULL THEN
        -- 今日尚未未抽奖，重置次数
        SET lottery_count = 0;
    END IF;

    IF lottery_count >= daily_limit THEN
        -- 当日次数达到了上限
        SET status = -1;
    ELSEIF user_pts < cost THEN
        -- 积分不足
        SET status = -2;
    ELSE
        -- 成功，记录一次并扣除积分
        SET lottery_count = lottery_count + 1;
        SET user_pts_new = user_pts - cost + prize;

        INSERT INTO gua_records (user_id, times_used, date)
        VALUES (p_uid, lottery_count, UTC_DATE)
        ON DUPLICATE KEY UPDATE times_used = lottery_count,
                                date       = UTC_DATE;

        UPDATE users
        SET points = user_pts_new
        WHERE user_id = p_uid;

        SET status = 1;
    END IF;

    SELECT status, user_pts, user_pts_new, lottery_count;
    COMMIT;
END;
