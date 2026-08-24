# Auto Test 项目

前后端分离项目：前端 Vue 3 + Vite，后端 Django。

## 解决 “Couldn't import Django” 报错

该报错表示当前 Python 环境里没有安装 Django，请按下面任一方式处理：

**方式一（推荐）：用项目自带的运行脚本（会自动创建 venv 并安装依赖）**

```bash
cd backend
chmod +x run.sh
./run.sh migrate
./run.sh runserver
```

**方式二：手动使用虚拟环境**

```bash
cd backend
python3 -m venv venv
source venv/bin/activate    # Windows: venv\Scripts\activate
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
```

之后每次运行 `manage.py` 时，要么先执行 `source venv/bin/activate` 再用 `python manage.py`，要么直接使用 `./run.sh runserver` 等。

## 目录结构

- **frontend/** — Vue 3 前端（Vite）
- **backend/**  — Django 后端

## 前端运行（必须先启动才能打开 Vue 页面）

**访问 http://127.0.0.1:5173 前，请先在本机启动前端开发服务器，否则会无法打开页面。**

```bash
cd frontend
yarn install   # 首次需要
yarn dev
```

启动成功后，用浏览器打开：**http://127.0.0.1:5173** 或 **http://localhost:5173**。  
默认会监听 5173 端口，并可在本机通过 127.0.0.1 访问；开发时请求 `/api/*` 会代理到后端 8000 端口。

## 后端运行

```bash
cd backend
./run.sh migrate
./run.sh runserver
```

或手动激活虚拟环境后执行：`source venv/bin/activate` → `pip install -r requirements.txt` → `python manage.py runserver`。

默认访问：http://127.0.0.1:8000  
健康检查：http://127.0.0.1:8000/api/common/health/

## 数据库（MySQL）

后端默认使用 **MySQL** 本地连接：

- **主机**：127.0.0.1  
- **端口**：3306  
- **用户**：root  
- **密码**：123456  
- **数据库名**：auto_test_db（需先创建）

**首次使用前：**

1. 启动 MySQL 服务。
2. 创建数据库（如未创建）：
   ```sql
   CREATE DATABASE auto_test_db CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
   ```
3. 在 backend 目录安装依赖并执行迁移（会创建 `z_user` 表）：
   ```bash
   cd backend
   source venv/bin/activate   # 或 run.sh
   pip install -r requirements.txt
   python manage.py migrate
   ```
4. 创建可登录用户（用户名与密码将写入 `z_user` 表）：
   ```bash
   python manage.py create_z_user 你的用户名 你的密码
   ```

**登录说明**：仅当 `z_user` 表中存在对应用户且密码正确时才能登录；登录成功后发放 7 天有效 token，页面内若 token 过期会提示并跳转回登录页。

如需修改连接信息，可设置环境变量：`DB_NAME`、`DB_USER`、`DB_PASSWORD`、`DB_HOST`、`DB_PORT`。

## 环境要求

- Node.js 18+
- Python 3.10+
- MySQL 5.7+ 或 8.x
- npm 或 pnpm
# auto_test_project
