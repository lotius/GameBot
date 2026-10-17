-- Idempotent MariaDB schema for GameBot. No existing tables are dropped.
CREATE TABLE IF NOT EXISTS found_instructions (
    instruction_id VARCHAR(191) PRIMARY KEY,
    title TEXT NOT NULL,
    page_url TEXT NOT NULL,
    found_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS gamebot_instruction_deliveries (
    channel_id BIGINT UNSIGNED NOT NULL,
    instruction_id VARCHAR(191) NOT NULL,
    sent_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    delivery_state VARCHAR(16) NOT NULL DEFAULT 'sent',
    PRIMARY KEY (channel_id, instruction_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS gamebot_guild_settings (
    guild_id BIGINT UNSIGNED PRIMARY KEY,
    instruction_channel_id BIGINT UNSIGNED NULL,
    bot_admin_role_id BIGINT UNSIGNED NULL,
    roll_logging_enabled BOOLEAN NOT NULL DEFAULT TRUE,
    spam_enabled BOOLEAN NOT NULL DEFAULT TRUE,
    spam_limit INT UNSIGNED NOT NULL DEFAULT 5,
    spam_window_seconds INT UNSIGNED NOT NULL DEFAULT 10,
    retention_enabled BOOLEAN NOT NULL DEFAULT FALSE,
    retention_days INT UNSIGNED NOT NULL DEFAULT 90,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS gamebot_channel_settings (
    guild_id BIGINT UNSIGNED NOT NULL,
    channel_id BIGINT UNSIGNED NOT NULL,
    rolls_enabled BOOLEAN NOT NULL DEFAULT TRUE,
    dddice_enabled BOOLEAN NOT NULL DEFAULT FALSE,
    dddice_destination VARCHAR(255) NULL,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (guild_id, channel_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS gamebot_guild_integrations (
    guild_id BIGINT UNSIGNED NOT NULL,
    integration VARCHAR(32) NOT NULL,
    encrypted_api_key TEXT NULL,
    default_destination VARCHAR(255) NULL,
    enabled BOOLEAN NOT NULL DEFAULT FALSE,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (guild_id, integration)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS gamebot_configuration_audit (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    guild_id BIGINT UNSIGNED NOT NULL,
    actor_id BIGINT UNSIGNED NOT NULL,
    setting_name VARCHAR(128) NOT NULL,
    channel_id BIGINT UNSIGNED NULL,
    old_value JSON NULL,
    new_value JSON NULL,
    changed_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX audit_guild_time (guild_id, changed_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS gamebot_rolls (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    message_id BIGINT UNSIGNED NOT NULL,
    guild_id BIGINT UNSIGNED NULL,
    channel_id BIGINT UNSIGNED NOT NULL,
    user_id BIGINT UNSIGNED NOT NULL,
    game_key VARCHAR(64) NOT NULL,
    command_name VARCHAR(64) NOT NULL,
    dice_count INT UNSIGNED NOT NULL,
    modifier BIGINT NOT NULL DEFAULT 0,
    definition_snapshot JSON NOT NULL,
    rolled_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY roll_message (message_id),
    INDEX roll_guild_game_time (guild_id, game_key, rolled_at),
    INDEX roll_game_time (game_key, rolled_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS gamebot_roll_results (
    roll_id BIGINT UNSIGNED NOT NULL,
    die_index INT UNSIGNED NOT NULL,
    dice_type VARCHAR(64) NOT NULL,
    face_id VARCHAR(191) NOT NULL,
    face_values JSON NOT NULL,
    PRIMARY KEY (roll_id, die_index),
    INDEX result_type_face (dice_type, face_id),
    CONSTRAINT gamebot_results_roll_fk FOREIGN KEY (roll_id) REFERENCES gamebot_rolls(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
