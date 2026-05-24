import urllib.parse

import psycopg2


def test_conn():
    password = urllib.parse.unquote("%242y%2410%24XE8gcR4ANOon%2FRYecWspB.D6.IH3rrAcFCi1Hk7NAvKP6HscnJSlC")
    project_ref = "znvixbtquyscpduxiavk"
    username = f"postgres.{project_ref}"
    
    hosts = [
        "aws-0-us-east-2.pooler.supabase.com",
    ]
    
    for host in hosts:
        print(f"Trying host: {host}")
        for port in [6543, 5432]:
            try:
                conn = psycopg2.connect(
                    database="postgres",
                    user=username,
                    password=password,
                    host=host,
                    port=port,
                    connect_timeout=5
                )
                print(f"SUCCESS connected to {host}:{port}")
                conn.close()
                return host, port
            except Exception as e:
                print(f"Failed {host}:{port} - {e}")
                
if __name__ == "__main__":
    test_conn()
