from sqlalchemy import create_engine
from pymilvus import connections

def test_mysql():
    print("⏳ 开始测试 MySQL 连接...")
    # 连接格式: mysql+pymysql://用户名:密码@主机IP:端口/数据库名
    mysql_url = "mysql+pymysql://root:root@127.0.0.1:3307/qa_system"
    try:
        engine = create_engine(mysql_url)
        # 尝试建立真实连接
        with engine.connect() as conn:
            print("✅ MySQL (端口 3307) 连接成功！")
    except Exception as e:
        print(f"❌ MySQL 连接失败，错误信息: {e}")

def test_milvus():
    print("\n⏳ 开始测试 Milvus 连接...")
    try:
        # 连接本地的 19530 端口
        connections.connect(alias="default", host="127.0.0.1", port="19530")
        print("✅ Milvus (端口 19530) 连接成功！")
        # 测试完毕后断开连接
        connections.disconnect("default")
    except Exception as e:
        print(f"❌ Milvus 连接失败，错误信息: {e}")

if __name__ == "__main__":
    test_mysql()
    test_milvus()