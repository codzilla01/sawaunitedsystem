-- Apply once after 0001; shared account login limits for serverless deployments.
CREATE TABLE login_budgets (
    key VARCHAR(64) NOT NULL,
    "window" INTEGER NOT NULL,
    attempts INTEGER NOT NULL,
    PRIMARY KEY (key, "window")
);
