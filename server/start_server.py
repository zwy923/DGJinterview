#!/usr/bin/env python3
"""
启动大狗叫面试助手后端服务
"""
import subprocess
import sys
import os

def main():
    print("启动大狗叫面试助手后端服务...")
    
    # 切换到server目录
    server_dir = os.path.join(os.path.dirname(__file__), 'server') if os.path.basename(os.path.dirname(__file__)) != 'server' else os.path.dirname(__file__)
    if os.path.exists(server_dir):
        os.chdir(server_dir)
    
    # 检查依赖
    try:
        import fastapi
        import uvicorn
        import funasr
        import numpy
        print("✅ 所有依赖已安装")
    except ImportError as e:
        print(f"❌ 缺少依赖: {e}")
        print("请运行: pip install -r requirements.txt")
        sys.exit(1)
    
    # 启动服务
    try:
        print("🌐 启动WebSocket服务器...")
        print("📡 服务地址: http://localhost:8000")
        print("🔗 WebSocket: ws://localhost:8000/ws/transcribe")
        print("💡 按 Ctrl+C 停止服务")
        print("-" * 50)
        
        subprocess.run([
            sys.executable, "-m", "uvicorn", 
            "main:app", 
            "--host", "0.0.0.0", 
            "--port", "8000", 
            "--reload"
        ])
    except KeyboardInterrupt:
        print("\n👋 服务已停止")
    except Exception as e:
        print(f"❌ 启动失败: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()

