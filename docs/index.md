---
layout: home

title: TG Manage 文档
description: Telegram 多账号面板、聊天中心与 TeleBox

hero:
  name: TG Manage
  text: Telegram 多账号管理面板
  tagline: 独立 Xray 节点 · 零点报告 · 聊天中心 · 内置 TeleBox
  image:
    src: /logo.svg
    alt: TG Manage
  actions:
    - theme: brand
      text: 快速开始
      link: /guide/quick-start
    - theme: alt
      text: 功能介绍
      link: /features
    - theme: alt
      text: v2.5.0 更新
      link: /releases/v2.5.0
    - theme: alt
      text: Docker 部署
      link: /deploy/docker
    - theme: alt
      text: GitHub
      link: https://github.com/hikling/TG-Manage

features:
  - icon: 👥
    title: 多账号管理
    details: 每账号分配独占的 Xray 订阅节点；卡片查看出口国家、公网 IP 与 TeleBox 状态。
  - icon: 🌐
    title: 主订阅与兜底订阅
    details: 主节点不足时使用兜底节点，仍不足则明确直连；延迟和连接异常经过复检再切换。
  - icon: 💬
    title: 聊天中心
    details: 按需开启群组会话，查看和发送消息。
  - icon: 🤖
    title: 私人机器人通知
    details: 私人 ID 可用 /me 和 /code 查询；每日零点另推送账号、线路与官方消息报告。
  - icon: 💾
    title: 加密登录备份
    details: 在账户管理手动导出或导入主账号的 .tglogin 授权文件，方便安全迁移。
  - icon: 🐳
    title: 源码部署
    details: Docker Compose 从当前仓库构建，数据保存在独立挂载目录。
---
