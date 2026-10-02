import Database from "better-sqlite3";
import path from "path";
import { createDirectoryInAssets } from "./pathHelpers";

class SendLogDB {
  private db: Database.Database;

  constructor(
    dbPath: string = path.join(createDirectoryInAssets("sendlog"), "sendlog.db")
  ) {
    this.db = new Database(dbPath);
    this.init();
  }

  private init(): void {
    this.db
      .prepare(
        `CREATE TABLE IF NOT EXISTS config (
          key TEXT PRIMARY KEY,
          value TEXT NOT NULL
        )`
      )
      .run();
  }

  public setTarget(target: string): void {
    this.db
      .prepare(
        `INSERT INTO config (key, value) VALUES ('target', ?)
         ON CONFLICT(key) DO UPDATE SET value = excluded.value`
      )
      .run(target);
  }

  public getTarget(): string {
    const row = this.db
      .prepare(`SELECT value FROM config WHERE key = 'target'`)
      .get() as { value: string } | undefined;
    return row ? row.value : "me";
  }

  public close(): void {
    this.db.close();
  }
}

export { SendLogDB };
