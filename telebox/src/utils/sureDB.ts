import Database from "better-sqlite3";
import { createDirectoryInAssets } from "./pathHelpers";
import path from "path";

interface UserRecord {
  uid: number;
  username: string;
}

interface ChatRecord {
  id: number;
  name: string;
}

// 新增消息记录接口
interface MsgRecord {
  id: number;
  msg: string;
  redirect?: string;
}

class SureDB {
  private db: Database.Database;

  constructor(
    dbPath: string = path.join(createDirectoryInAssets("sure"), "sure.db")
  ) {
    this.db = new Database(dbPath);
    this.init();
  }

  // 初始化表结构
  private init(): void {
    this.db
      .prepare(
        `
      CREATE TABLE IF NOT EXISTS users (
        uid INTEGER PRIMARY KEY,
        username TEXT NOT NULL
      )
    `
      )
      .run();

    // 新增 chats 表
    this.db
      .prepare(
        `
      CREATE TABLE IF NOT EXISTS chats (
        id INTEGER PRIMARY KEY,
        name TEXT NOT NULL
      )
    `
      )
      .run();

    // 新增 msgs 表，支持自增 id
    this.db
      .prepare(
        `
      CREATE TABLE IF NOT EXISTS msgs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        msg TEXT NOT NULL UNIQUE,
        redirect TEXT
      )
    `
      )
      .run();
  }

  /**
   * 添加或更新用户
   */
  public add(uid: number, username: string): void {
    const stmt = this.db.prepare(`
      INSERT INTO users (uid, username)
      VALUES (?, ?)
      ON CONFLICT(uid) DO UPDATE SET username = excluded.username
    `);
    stmt.run(uid, username);
  }

  /**
   * 删除用户
   */
  public del(uid: number): boolean {
    const info = this.db
      .prepare(
        `
      DELETE FROM users WHERE uid = ?
    `
      )
      .run(uid);
    return info.changes > 0;
  }

  /**
   * 列出所有用户
   */
  public ls(): UserRecord[] {
    return this.db
      .prepare<[], UserRecord>(
        `
        SELECT uid, username FROM users
        ORDER BY uid ASC
      `
      )
      .all();
  }

  // 添加或更新聊天
  public addChat(id: number, name: string): void {
    this.db
      .prepare(
        `
        INSERT INTO chats (id, name)
        VALUES (?, ?)
        ON CONFLICT(id) DO UPDATE SET name = excluded.name
      `
      )
      .run(id, name);
  }

  // 删除聊天
  public delChat(id: number): boolean {
    const info = this.db
      .prepare(
        `
        DELETE FROM chats WHERE id = ?
      `
      )
      .run(id);
    return info.changes > 0;
  }

  // 列出所有聊天
  public lsChats(): ChatRecord[] {
    return this.db
      .prepare<[], ChatRecord>(
        `
          SELECT id, name FROM chats
          ORDER BY id ASC
        `
      )
      .all();
  }

  // 新增：添加消息
  public addMsg(msg: string, redirectMsg?: string): void {
    this.db
      .prepare(
        `
        INSERT INTO msgs (msg, redirect)
        VALUES (?, ?)
        ON CONFLICT(msg) DO UPDATE SET redirect = excluded.redirect
      `
      )
      .run(msg, redirectMsg);
  }

  // 删除消息
  public delMsg(id: number): boolean {
    const info = this.db
      .prepare(
        `
        DELETE FROM msgs WHERE id = ?
      `
      )
      .run(id);
    return info.changes > 0;
  }

  // 列出所有消息
  public lsMsgs(): MsgRecord[] {
    return this.db
      .prepare<[], MsgRecord>(
        `
        SELECT id, msg, redirect FROM msgs ORDER BY id ASC
      `
      )
      .all();
  }

  /**
   * 关闭数据库
   */
  public close(): void {
    this.db.close();
  }
}

export { SureDB, UserRecord, ChatRecord, MsgRecord };
