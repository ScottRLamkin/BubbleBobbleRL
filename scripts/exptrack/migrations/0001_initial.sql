-- Experiment/run configuration and history store (docs/experiment-tracking.md).
-- Configuration records are immutable once written: changes become new
-- experiment revisions or new runs, and lifecycle is an append-only event log.

CREATE TABLE game_versions (
  id            TEXT PRIMARY KEY,          -- 'game-' + first 12 hex of source_hash
  name          TEXT NOT NULL UNIQUE,      -- human-readable name
  source_hash   TEXT NOT NULL UNIQUE,      -- sha256 over the game package files (path + content, sorted)
  source_commit TEXT,                      -- git commit the files were taken from, when known
  files_json    TEXT NOT NULL,             -- {relative path: sha256}
  description   TEXT NOT NULL,
  created_at    TEXT NOT NULL
);

CREATE TABLE experiments (
  id          TEXT PRIMARY KEY,            -- 'exp-' + hash of the name: stable across imports
  name        TEXT NOT NULL UNIQUE,
  question    TEXT NOT NULL,
  origin      TEXT NOT NULL CHECK (origin IN ('registered', 'historical_import')),
  created_at  TEXT NOT NULL
);

CREATE TABLE experiment_revisions (
  id                 TEXT PRIMARY KEY,
  experiment_id      TEXT NOT NULL REFERENCES experiments(id),
  revision           INTEGER NOT NULL CHECK (revision >= 1),
  parent_revision_id TEXT REFERENCES experiment_revisions(id),
  game_version_id    TEXT NOT NULL REFERENCES game_versions(id),
  config_json        TEXT NOT NULL,        -- canonical JSON of every experiment hyperparameter
  config_sha256      TEXT NOT NULL,
  change_note        TEXT NOT NULL,
  created_at         TEXT NOT NULL,
  UNIQUE (experiment_id, revision),
  UNIQUE (experiment_id, config_sha256)
);

CREATE TABLE experiment_params (
  revision_id TEXT NOT NULL REFERENCES experiment_revisions(id),
  key         TEXT NOT NULL,               -- namespaced, e.g. 'evaluation.seeds'
  value_json  TEXT NOT NULL,               -- JSON-encoded typed value
  value_type  TEXT NOT NULL,               -- int | float | bool | str | null | list | object
  unit        TEXT,
  PRIMARY KEY (revision_id, key)
);

CREATE TABLE runs (
  id             TEXT PRIMARY KEY,         -- 'run-' + hash of (revision, run_key)
  revision_id    TEXT NOT NULL REFERENCES experiment_revisions(id),
  run_key        TEXT NOT NULL,            -- identity within the revision, e.g. 'arm=mlp512x2/seed=4401'
  arm            TEXT NOT NULL,
  config_json    TEXT NOT NULL,            -- complete effective trainer configuration, resolved before dispatch
  config_sha256  TEXT NOT NULL,
  overrides_json TEXT NOT NULL,            -- the run's explicit overrides (arm + run level)
  origin         TEXT NOT NULL CHECK (origin IN ('registered', 'historical_import')),
  created_at     TEXT NOT NULL,
  UNIQUE (revision_id, run_key)
);

CREATE TABLE run_params (
  run_id      TEXT NOT NULL REFERENCES runs(id),
  key         TEXT NOT NULL,               -- namespaced, e.g. 'reward.death_penalty'
  trainer_key TEXT,                        -- the trainer's own name, e.g. 'death_penalty'; NULL when derived
  value_json  TEXT NOT NULL,
  value_type  TEXT NOT NULL,
  unit        TEXT,
  active      INTEGER NOT NULL CHECK (active IN (0, 1)),  -- 0: gated off by another setting (value kept)
  gated_by    TEXT,                        -- the governing key, when gated
  source      TEXT NOT NULL,               -- provenance: experiment.shared | experiment.arm | run.override | derived | historical
  PRIMARY KEY (run_id, key)
);

CREATE TABLE run_attempts (
  id                   TEXT PRIMARY KEY,   -- run id + '-a' + attempt
  run_id               TEXT NOT NULL REFERENCES runs(id),
  attempt              INTEGER NOT NULL CHECK (attempt >= 1),
  run_dir              TEXT,
  mlflow_tracking_uri  TEXT,
  mlflow_experiment_id TEXT,
  mlflow_run_id        TEXT,
  created_at           TEXT NOT NULL,
  UNIQUE (run_id, attempt)
);

CREATE TABLE evaluations (
  id                TEXT PRIMARY KEY,      -- 'eval-' + hash of (run, checkpoint, protocol)
  run_id            TEXT NOT NULL REFERENCES runs(id),
  attempt_id        TEXT REFERENCES run_attempts(id),
  game_version_id   TEXT NOT NULL REFERENCES game_versions(id),
  checkpoint_path   TEXT NOT NULL,
  checkpoint_sha256 TEXT NOT NULL,
  protocol_json     TEXT NOT NULL,         -- full effective protocol
  protocol_sha256   TEXT NOT NULL,
  role              TEXT NOT NULL,         -- screen | tuning | final | display | diagnostic
  metric_definition TEXT NOT NULL,
  metric_version    TEXT NOT NULL,
  results_json      TEXT NOT NULL,
  raw_path          TEXT,
  raw_sha256        TEXT,
  origin            TEXT NOT NULL CHECK (origin IN ('registered', 'historical_import')),
  created_at        TEXT NOT NULL,
  UNIQUE (run_id, checkpoint_sha256, protocol_sha256)
);

CREATE TABLE evaluation_params (
  evaluation_id TEXT NOT NULL REFERENCES evaluations(id),
  key           TEXT NOT NULL,
  value_json    TEXT NOT NULL,
  value_type    TEXT NOT NULL,
  unit          TEXT,
  PRIMARY KEY (evaluation_id, key)
);

CREATE TABLE artifacts (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  experiment_id TEXT REFERENCES experiments(id),
  run_id        TEXT REFERENCES runs(id),
  attempt_id    TEXT REFERENCES run_attempts(id),
  evaluation_id TEXT REFERENCES evaluations(id),
  kind          TEXT NOT NULL,             -- checkpoint | optimizer | config | train_summary | eval_raw | gallery | source_snapshot | manifest | outbox
  path          TEXT NOT NULL,
  sha256        TEXT,
  note          TEXT NOT NULL DEFAULT '',
  created_at    TEXT NOT NULL,
  UNIQUE (kind, path, sha256)
);

CREATE TABLE events (                      -- append-only lifecycle and change log
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  ts            TEXT NOT NULL,
  experiment_id TEXT REFERENCES experiments(id),
  revision_id   TEXT REFERENCES experiment_revisions(id),
  run_id        TEXT REFERENCES runs(id),
  attempt_id    TEXT REFERENCES run_attempts(id),
  evaluation_id TEXT REFERENCES evaluations(id),
  event         TEXT NOT NULL,
  detail_json   TEXT NOT NULL
);

CREATE INDEX events_run ON events(run_id, id);
CREATE INDEX events_attempt ON events(attempt_id, id);
CREATE INDEX run_params_key ON run_params(key);
CREATE INDEX experiment_params_key ON experiment_params(key);

-- Immutability: configuration rows and the event log are never rewritten.
CREATE TRIGGER game_versions_no_update BEFORE UPDATE ON game_versions BEGIN SELECT RAISE(ABORT, 'game versions are immutable'); END;
CREATE TRIGGER experiment_revisions_no_update BEFORE UPDATE ON experiment_revisions BEGIN SELECT RAISE(ABORT, 'experiment revisions are immutable'); END;
CREATE TRIGGER experiment_revisions_no_delete BEFORE DELETE ON experiment_revisions BEGIN SELECT RAISE(ABORT, 'experiment revisions are immutable'); END;
CREATE TRIGGER experiment_params_no_update BEFORE UPDATE ON experiment_params BEGIN SELECT RAISE(ABORT, 'experiment parameters are immutable'); END;
CREATE TRIGGER experiment_params_no_delete BEFORE DELETE ON experiment_params BEGIN SELECT RAISE(ABORT, 'experiment parameters are immutable'); END;
CREATE TRIGGER runs_no_update BEFORE UPDATE ON runs BEGIN SELECT RAISE(ABORT, 'runs are immutable; register a new run'); END;
CREATE TRIGGER runs_no_delete BEFORE DELETE ON runs BEGIN SELECT RAISE(ABORT, 'runs are immutable'); END;
CREATE TRIGGER run_params_no_update BEFORE UPDATE ON run_params BEGIN SELECT RAISE(ABORT, 'run parameters are immutable'); END;
CREATE TRIGGER run_params_no_delete BEFORE DELETE ON run_params BEGIN SELECT RAISE(ABORT, 'run parameters are immutable'); END;
CREATE TRIGGER run_attempts_no_update BEFORE UPDATE ON run_attempts BEGIN SELECT RAISE(ABORT, 'attempts are immutable'); END;
CREATE TRIGGER evaluations_no_update BEFORE UPDATE ON evaluations BEGIN SELECT RAISE(ABORT, 'evaluations are immutable'); END;
CREATE TRIGGER evaluation_params_no_update BEFORE UPDATE ON evaluation_params BEGIN SELECT RAISE(ABORT, 'evaluation parameters are immutable'); END;
CREATE TRIGGER events_no_update BEFORE UPDATE ON events BEGIN SELECT RAISE(ABORT, 'the event log is append-only'); END;
CREATE TRIGGER events_no_delete BEFORE DELETE ON events BEGIN SELECT RAISE(ABORT, 'the event log is append-only'); END;
