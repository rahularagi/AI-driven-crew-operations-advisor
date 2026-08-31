-- crew_ops database schema

-- ─── Crew Profile ─────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS crew_members (
    crew_id             VARCHAR(10)     PRIMARY KEY,
    employee_id         VARCHAR(20)     NOT NULL UNIQUE,
    full_name           VARCHAR(100)    NOT NULL,
    designation         VARCHAR(30)     NOT NULL,
    role                VARCHAR(10)     NOT NULL CHECK (role IN ('PILOT', 'CABIN')),
    home_base           VARCHAR(4)      NOT NULL,
    date_of_joining     DATE            NOT NULL,
    seniority_number    INTEGER         NOT NULL,
    employment_status   VARCHAR(10)     NOT NULL DEFAULT 'ACTIVE',
    phone               VARCHAR(20),
    email               VARCHAR(100),
    created_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW()
);

-- ─── Crew Licenses ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS crew_licenses (
    id                  SERIAL          PRIMARY KEY,
    crew_id             VARCHAR(10)     NOT NULL REFERENCES crew_members(crew_id),
    aircraft_type       VARCHAR(10)     NOT NULL,
    expiry_date         DATE            NOT NULL,
    medical_expiry      DATE,
    simulator_check_due DATE,
    created_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    UNIQUE (crew_id, aircraft_type)
);

-- ─── FTL State ────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS crew_ftl_states (
    crew_id                             VARCHAR(10)     PRIMARY KEY REFERENCES crew_members(crew_id),
    role                                VARCHAR(10)     NOT NULL,
    status                              VARCHAR(15)     NOT NULL DEFAULT 'AVAILABLE',
    duty_start_time                     TIMESTAMPTZ,
    duty_end_time                       TIMESTAMPTZ,
    projected_duty_period_end           TIMESTAMPTZ,
    flight_hours_current_duty           FLOAT           NOT NULL DEFAULT 0.0,
    sectors_current_duty                INTEGER         NOT NULL DEFAULT 0,
    rest_start_time                     TIMESTAMPTZ,
    last_rest_end_time                  TIMESTAMPTZ,
    rest_hours_available                FLOAT           NOT NULL DEFAULT 0.0,
    flight_hours_28_day                 FLOAT           NOT NULL DEFAULT 0.0,
    duty_hours_7_day                    FLOAT           NOT NULL DEFAULT 0.0,
    duty_hours_28_day                   FLOAT           NOT NULL DEFAULT 0.0,
    consecutive_duty_days               INTEGER         NOT NULL DEFAULT 0,
    last_weekly_rest_end                TIMESTAMPTZ,
    max_duty_period_hours               FLOAT           NOT NULL DEFAULT 13.0,
    circadian_low_window_encroachment   BOOLEAN         NOT NULL DEFAULT FALSE,
    duty_period_reduction_hours         FLOAT           NOT NULL DEFAULT 0.0,
    duty_period_extended                BOOLEAN         NOT NULL DEFAULT FALSE,
    duty_period_extension_hours         FLOAT           NOT NULL DEFAULT 0.0,
    home_base                           VARCHAR(4)      NOT NULL,
    current_airport                     VARCHAR(4)      NOT NULL,
    at_home_base                        BOOLEAN         NOT NULL DEFAULT TRUE,
    rest_type                           VARCHAR(15),
    earliest_checkout                   TIMESTAMPTZ,
    last_updated                        TIMESTAMPTZ     NOT NULL DEFAULT NOW()
);

-- ─── Crew Leave ───────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS crew_leave_records (
    id          SERIAL          PRIMARY KEY,
    crew_id     VARCHAR(10)     NOT NULL REFERENCES crew_members(crew_id),
    leave_type  VARCHAR(20)     NOT NULL,
    start_date  DATE            NOT NULL,
    end_date    DATE            NOT NULL,
    created_at  TIMESTAMPTZ     NOT NULL DEFAULT NOW()
);

-- ─── Reserve Schedule ─────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS crew_reserve_schedule (
    reserve_id          VARCHAR(10)     PRIMARY KEY,
    crew_id             VARCHAR(10)     NOT NULL REFERENCES crew_members(crew_id),
    date                DATE            NOT NULL,
    standby_start       TIMESTAMPTZ     NOT NULL,
    standby_end         TIMESTAMPTZ     NOT NULL,
    base_airport        VARCHAR(4)      NOT NULL,
    callable_within     INTEGER         NOT NULL DEFAULT 120,
    status              VARCHAR(15)     NOT NULL DEFAULT 'SCHEDULED',
    activated_for       VARCHAR(50),
    created_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW()
);

-- ─── Flight Legs ──────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS flight_legs (
    leg_id                  VARCHAR(50)     PRIMARY KEY,
    flight_number           VARCHAR(10)     NOT NULL,
    origin_iata             VARCHAR(3)      NOT NULL,
    origin_icao             VARCHAR(4)      NOT NULL,
    destination_iata        VARCHAR(3)      NOT NULL,
    destination_icao        VARCHAR(4)      NOT NULL,
    scheduled_departure     TIMESTAMPTZ     NOT NULL,
    scheduled_arrival       TIMESTAMPTZ     NOT NULL,
    estimated_arrival       TIMESTAMPTZ,
    actual_departure        TIMESTAMPTZ,
    actual_arrival          TIMESTAMPTZ,
    aircraft_type           VARCHAR(10)     NOT NULL,
    aircraft_registration   VARCHAR(10)     NOT NULL,
    status                  VARCHAR(15)     NOT NULL DEFAULT 'SCHEDULED',
    delay_status            VARCHAR(15)     NOT NULL DEFAULT 'ON_TIME',
    delay_minutes           INTEGER         NOT NULL DEFAULT 0,
    created_at              TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    updated_at              TIMESTAMPTZ     NOT NULL DEFAULT NOW()
);

-- ─── Leg Crew Assignments ─────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS leg_crew_assignments (
    id          SERIAL          PRIMARY KEY,
    leg_id      VARCHAR(50)     NOT NULL REFERENCES flight_legs(leg_id),
    crew_id     VARCHAR(10)     NOT NULL REFERENCES crew_members(crew_id),
    created_at  TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    UNIQUE (leg_id, crew_id)
);

-- ─── Crew Unavailability ──────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS crew_unavailability (
    id              SERIAL          PRIMARY KEY,
    crew_id         VARCHAR(10)     NOT NULL REFERENCES crew_members(crew_id),
    reason          VARCHAR(30)     NOT NULL,
    from_datetime   TIMESTAMPTZ     NOT NULL,
    to_datetime     TIMESTAMPTZ     NOT NULL,
    created_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW()
);

-- ─── Roster Leg ───────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS roster_leg (
    id              SERIAL          PRIMARY KEY,
    leg_id          VARCHAR(50)     NOT NULL REFERENCES flight_legs(leg_id),
    plan_start      DATE            NOT NULL,
    plan_end        DATE            NOT NULL,
    status          VARCHAR(15)     NOT NULL DEFAULT 'DRAFT',
    triggered_by    VARCHAR(50)     NOT NULL,
    created_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    UNIQUE (leg_id, plan_start)
);

-- ─── Roster Crew Assignment ───────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS roster_crew_assignment (
    id                      SERIAL          PRIMARY KEY,
    leg_id                  VARCHAR(50)     NOT NULL REFERENCES flight_legs(leg_id),
    crew_id                 VARCHAR(10)     NOT NULL REFERENCES crew_members(crew_id),
    status                  VARCHAR(15)     NOT NULL DEFAULT 'DRAFT',
    assigned_by             VARCHAR(50)     NOT NULL,
    assigned_at             TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    replaced_by             VARCHAR(10)     REFERENCES crew_members(crew_id),
    replaced_at             TIMESTAMPTZ,
    invalidation_reason     VARCHAR(50),
    UNIQUE (leg_id, crew_id)
);
