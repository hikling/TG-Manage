import Database from "better-sqlite3";
import { createDirectoryInAssets } from "./pathHelpers";
import path from "path";

interface AliasRecord {
  original: string;
  final: string;
}

class AliasDB {
  private db: Database.Database;

  constructor(
    dbPath: string = path.join(createDirectoryInAssets("alias"), "alias.db")
  ) {
    this.db = new Database(dbPath);
    this.init();
  }

  // 初始化表结构
  private init(): void {
    this.db
      .prepare(
        `
      CREATE TABLE IF NOT EXISTS aliases (
        original TEXT PRIMARY KEY,
        final TEXT NOT NULL
      )
    `
      )
      .run();
  }

  /**
   * 设置别名（如果已存在则更新）
   */
  public set(original: string, final: string): void {
    const stmt = this.db.prepare(`
      INSERT INTO aliases (original, final)
      VALUES (?, ?)
      ON CONFLICT(original) DO UPDATE SET final = excluded.final
    `);
    stmt.run(original, final);
  }

  /**
   * 列出所有别名
   */
  public list(): AliasRecord[] {
    return this.db
      .prepare<[], AliasRecord>(
        `
      SELECT original, final FROM aliases
    `
      )
      .all();
  }

  /**
   * 删除别名
   */
  public del(original: string): boolean {
    const info = this.db
      .prepare(`DELETE FROM aliases WHERE original = ?`)
      .run(original);
    return info.changes > 0;
  }

  /**
   * 根据 original 获取 final
   * @param original 原始值
   * @returns final 字符串，找不到则返回 null
   */
  public get(original: string): string | null {
    const row = this.db
      .prepare<[string], { final: string }>(
        "SELECT final FROM aliases WHERE original = ?"
      )
      .get(original);
    return row ? row.final : null;
  }
  /**
   * 根据 final 获取所有 original
   * @param final
   * @returns original 字符串数组，找不到则返回空数组
   */
  public getOriginal(final: string): string[] {
    const rows = this.db
      .prepare<[string], { original: string }>(
        `
      SELECT original FROM aliases WHERE final = ?
    `
      )
      .all(final);
    return rows.map((row) => row.original);
  }

  /**
   * 关闭数据库
   */
  public close(): void {
    this.db.close();
  }
}

export { AliasDB };
