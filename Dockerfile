# 使用 Python 3.11 官方镜像（稳定版本，不会缺 cgi 模块）
FROM python:3.11-slim

# 设置工作目录
WORKDIR /app

# 复制依赖文件
COPY requirements.txt .

# 安装依赖（使用清华镜像加速）
RUN pip install --no-cache-dir -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple

# 复制项目文件
COPY readingapp.py .
COPY templates ./templates

# 暴露端口
EXPOSE 5000

# 启动命令
CMD ["gunicorn", "readingapp:app", "--bind", "0.0.0.0:5000"]
