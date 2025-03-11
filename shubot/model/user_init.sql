DROP PROCEDURE IF EXISTS shubot_common_user_update_pts;
CREATE PROCEDURE shubot_common_user_update_pts(IN p_uid INT8, IN p_delta INT8)
    -- 用户积分更改
    -- p_uid: 用户ID
    -- p_delta: 变化量
BEGIN
    DECLARE found INT DEFAULT 0;
    DECLARE status INT DEFAULT 0;
    DECLARE old_pts INT8 DEFAULT 0;
    DECLARE new_pts INT8 DEFAULT 0;

    DECLARE EXIT HANDLER FOR SQLEXCEPTION BEGIN
        ROLLBACK;
        SELECT 0, 0, 0;
    END;

    START TRANSACTION;

    SELECT 1, u.points
    INTO found, old_pts
    FROM users u
    WHERE u.user_id = p_uid;

    IF found = 0 THEN
        -- 目标不存在，建立用户。
        SET old_pts = 0;
        SET new_pts = GREATEST(p_delta, 0);

        INSERT INTO users (user_id, points)
        VALUES (p_uid, new_pts);

        SET status = 1;
    ELSE
        SET new_pts = GREATEST(old_pts + p_delta, 0);
        UPDATE users
        SET points = new_pts
        WHERE user_id = p_uid;

        SET status = 2;
    END IF;

    SELECT status, old_pts, new_pts;
    COMMIT;
END;

DROP PROCEDURE IF EXISTS shubot_common_user_update_pills;
CREATE PROCEDURE shubot_common_user_update_pills(IN p_uid INT8, IN p_delta INT8)
    -- 修仙/药丸更改
    -- p_uid: 用户ID
    -- p_delta: 变化量
BEGIN
    DECLARE found INT DEFAULT 0;
    DECLARE status INT DEFAULT 0;
    DECLARE old_pills INT8 DEFAULT 0;
    DECLARE new_pills INT8 DEFAULT 0;

    DECLARE EXIT HANDLER FOR SQLEXCEPTION BEGIN
        ROLLBACK;
        SELECT 0, 0, 0;
    END;

    START TRANSACTION;

    SELECT 1, uc.pills
    INTO found, old_pills
    FROM user_cultivation uc
    WHERE uc.user_id = p_uid;

    IF found = 0 THEN
        -- 目标不存在，建立修仙档案。
        SET old_pills = 0;
        SET new_pills = GREATEST(p_delta, 0);

        INSERT INTO user_cultivation (user_id, pills, stage, next_cost)
        VALUES (p_uid, new_pills, 0, 10);

        SET status = 1;
    ELSE
        SET new_pills = GREATEST(old_pills + p_delta, 0);
        UPDATE user_cultivation
        SET pills = new_pills
        WHERE user_id = p_uid;

        SET status = 2;
    END IF;

    SELECT status, old_pills, new_pills;
    COMMIT;
END;
