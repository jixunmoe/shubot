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

    -- 没钱了
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
