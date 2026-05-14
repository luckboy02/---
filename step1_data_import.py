# -*- coding: utf-8 -*-
"""
============================================================
Step 1: 数据入库（MySQL）
 - 复制 CSV 到 MySQL 上传目录
 - 创建 资金流入流出 数据库及 6 张表
 - LOAD DATA INFILE 导入 4 个 CSV
 - 数据验证
============================================================
"""

import pymysql
import os
import shutil
import time

# =====================================================
# 0. 配置参数
# =====================================================

MYSQL_HOST = 'localhost'
MYSQL_PORT = 3306
MYSQL_USER = 'root'
MYSQL_PASSWORD = 'wq010205'
MYSQL_DB = '资金流入流出'

# MySQL 的 secure_file_priv 目录（LOAD DATA INFILE 只能读此目录下的文件）
MYSQL_UPLOAD_DIR = 'C:/ProgramData/MySQL/MySQL Server 8.0/Uploads/'

# CSV 源文件目录
CSV_SOURCE_DIR = 'D:/Modeling code/数据分析项目/资金流入流出预测/Purchase Redemption Data'

# 四个 CSV 文件名（已改为中文）
CSV_FILES = [
    '用户余额表.csv',
    '用户画像表.csv',
    '货币基金日收益率表.csv',
    '银行间拆借利率表.csv',
]


def get_connection(use_db=False):
    """获取 MySQL 连接"""
    kwargs = dict(
        host=MYSQL_HOST, port=MYSQL_PORT,
        user=MYSQL_USER, password=MYSQL_PASSWORD,
        charset='utf8mb4', local_infile=True,
    )
    if use_db:
        kwargs['database'] = MYSQL_DB
    return pymysql.connect(**kwargs)


def copy_csv_files():
    """将 CSV 文件复制到 MySQL 的上传目录（secure_file_priv）"""
    print('=' * 60)
    print('Step 1/4: 复制 CSV 文件到 MySQL 上传目录')
    print(f'  目标目录: {MYSQL_UPLOAD_DIR}')
    print('=' * 60)

    for fname in CSV_FILES:
        src = os.path.join(CSV_SOURCE_DIR, fname)
        dst = os.path.join(MYSQL_UPLOAD_DIR, fname)
        if not os.path.exists(src):
            print(f'  [错误] 源文件不存在: {src}')
            continue
        fsize_mb = os.path.getsize(src) / (1024 * 1024)
        print(f'  复制 {fname} ({fsize_mb:.1f} MB)...')
        shutil.copy2(src, dst)
        print(f'    -> 完成')
    print()


def create_database_and_tables():
    """创建数据库 资金流入流出 及 6 张表"""
    print('=' * 60)
    print('Step 2/4: 建库建表')
    print('=' * 60)

    conn = get_connection(use_db=False)
    cursor = conn.cursor()

    # ---- 建库 ----
    cursor.execute('DROP DATABASE IF EXISTS `资金流入流出`')
    cursor.execute(
        'CREATE DATABASE `资金流入流出` '
        'DEFAULT CHARACTER SET utf8mb4 '
        'DEFAULT COLLATE utf8mb4_general_ci'
    )
    cursor.execute('USE `资金流入流出`')
    print('  数据库 资金流入流出 创建成功')

    # ---- 1) 用户余额表（主表） ----
    cursor.execute('''
        CREATE TABLE `用户余额表` (
            `用户ID`        INT           NOT NULL,
            `报告日期`      DATE          NOT NULL,
            `今日余额`      DECIMAL(20,2) DEFAULT 0,
            `昨日余额`      DECIMAL(20,2) DEFAULT 0,
            `总申购金额`    DECIMAL(20,2) DEFAULT 0,
            `直接申购金额`  DECIMAL(20,2) DEFAULT 0,
            `余额申购金额`  DECIMAL(20,2) DEFAULT 0,
            `银行卡申购金额` DECIMAL(20,2) DEFAULT 0,
            `总赎回金额`    DECIMAL(20,2) DEFAULT 0,
            `消费金额`      DECIMAL(20,2) DEFAULT 0,
            `转账金额`      DECIMAL(20,2) DEFAULT 0,
            `转入余额宝金额` DECIMAL(20,2) DEFAULT 0,
            `转出到银行卡金额` DECIMAL(20,2) DEFAULT 0,
            `分享金额`      DECIMAL(20,2) DEFAULT 0,
            `类别1`         DECIMAL(20,2) DEFAULT NULL,
            `类别2`         DECIMAL(20,2) DEFAULT NULL,
            `类别3`         DECIMAL(20,2) DEFAULT NULL,
            `类别4`         DECIMAL(20,2) DEFAULT NULL,
            PRIMARY KEY (`用户ID`, `报告日期`)
        ) ENGINE=InnoDB
    ''')
    print('  表 用户余额表 创建成功')

    # ---- 2) 用户画像表 ----
    cursor.execute('''
        CREATE TABLE `用户画像表` (
            `用户ID`       INT          NOT NULL PRIMARY KEY,
            `性别`         TINYINT      DEFAULT NULL,
            `城市`         INT          DEFAULT NULL,
            `星座`         VARCHAR(20)  DEFAULT NULL
        ) ENGINE=InnoDB
    ''')
    print('  表 用户画像表 创建成功')

    # ---- 3) 收益率表 ----
    cursor.execute('''
        CREATE TABLE `收益率表` (
            `日期`              DATE   NOT NULL PRIMARY KEY,
            `万份收益`          DOUBLE DEFAULT NULL,
            `七日年化收益率`    DOUBLE DEFAULT NULL
        ) ENGINE=InnoDB
    ''')
    print('  表 收益率表 创建成功')

    # ---- 4) 拆借利率表 ----
    cursor.execute('''
        CREATE TABLE `拆借利率表` (
            `日期`        DATE   NOT NULL PRIMARY KEY,
            `隔夜利率`    DOUBLE DEFAULT NULL,
            `一周利率`    DOUBLE DEFAULT NULL,
            `两周利率`    DOUBLE DEFAULT NULL,
            `一月利率`    DOUBLE DEFAULT NULL,
            `三月利率`    DOUBLE DEFAULT NULL,
            `六月利率`    DOUBLE DEFAULT NULL,
            `九月利率`    DOUBLE DEFAULT NULL,
            `一年利率`    DOUBLE DEFAULT NULL
        ) ENGINE=InnoDB
    ''')
    print('  表 拆借利率表 创建成功')

    # ---- 5) 日历表 ----
    cursor.execute('''
        CREATE TABLE `日历表` (
            `报告日期` DATE NOT NULL PRIMARY KEY
        )
    ''')
    # 递归生成 2013-07-01 ~ 2014-09-30 的所有日期
    cursor.execute('''
        INSERT INTO `日历表` (`报告日期`)
        WITH RECURSIVE dates AS (
            SELECT DATE('2013-07-01') AS dt
            UNION ALL
            SELECT DATE_ADD(dt, INTERVAL 1 DAY)
            FROM dates
            WHERE dt < '2014-09-30'
        )
        SELECT dt FROM dates
    ''')
    conn.commit()
    cursor.execute('SELECT COUNT(*) FROM `日历表`')
    print(f'  表 日历表 创建成功，共 {cursor.fetchone()[0]} 天')

    # ---- 6) 节假日表 ----
    cursor.execute('''
        CREATE TABLE `节假日表` (
            `节假日日期` DATE        NOT NULL PRIMARY KEY,
            `节假日名称` VARCHAR(50) NOT NULL
        )
    ''')
    cursor.execute('''
        INSERT INTO `节假日表` VALUES
        ('2013-09-19','中秋节'),('2013-09-20','中秋节'),('2013-09-21','中秋节'),
        ('2013-10-01','国庆节'),('2013-10-02','国庆节'),('2013-10-03','国庆节'),
        ('2013-10-04','国庆节'),('2013-10-05','国庆节'),('2013-10-06','国庆节'),
        ('2013-10-07','国庆节'),
        ('2014-01-01','元旦'),
        ('2014-01-31','春节'),('2014-02-01','春节'),('2014-02-02','春节'),
        ('2014-02-03','春节'),('2014-02-04','春节'),('2014-02-05','春节'),
        ('2014-02-06','春节'),
        ('2014-04-05','清明节'),('2014-04-06','清明节'),('2014-04-07','清明节'),
        ('2014-05-01','劳动节'),('2014-05-02','劳动节'),('2014-05-03','劳动节'),
        ('2014-05-31','端午节'),('2014-06-01','端午节'),('2014-06-02','端午节'),
        ('2014-09-06','中秋节'),('2014-09-07','中秋节'),('2014-09-08','中秋节')
    ''')
    conn.commit()
    print('  表 节假日表 创建成功')

    conn.close()
    print('  所有表创建完毕\n')


def load_csv_data():
    """使用 LOAD DATA INFILE 导入 4 个 CSV 文件"""
    print('=' * 60)
    print('Step 3/4: 导入 CSV 数据')
    print('=' * 60)

    conn = get_connection(use_db=True)
    cursor = conn.cursor()

    # ----- 用户余额表 -----
    # 日期字段在 CSV 中是 YYYYMMDD 整数，需用 STR_TO_DATE 转换
    # 类别1~4 中的空字符串需转为 NULL
    print('  导入 用户余额表.csv (150 MB，预计1-3分钟)...')
    t0 = time.time()
    cursor.execute(f'''
        LOAD DATA INFILE '{MYSQL_UPLOAD_DIR}用户余额表.csv'
        INTO TABLE `用户余额表`
        FIELDS TERMINATED BY ',' OPTIONALLY ENCLOSED BY '"'
        LINES TERMINATED BY '\\r\\n'
        IGNORE 1 ROWS
        (`用户ID`, @raw_date, `今日余额`, `昨日余额`,
         `总申购金额`, `直接申购金额`, `余额申购金额`, `银行卡申购金额`,
         `总赎回金额`, `消费金额`, `转账金额`, `转入余额宝金额`, `转出到银行卡金额`,
         `分享金额`, @c1, @c2, @c3, @c4)
        SET `报告日期` = STR_TO_DATE(@raw_date, '%Y%m%d'),
            `类别1` = NULLIF(@c1, ''),
            `类别2` = NULLIF(@c2, ''),
            `类别3` = NULLIF(@c3, ''),
            `类别4` = NULLIF(@c4, '')
    ''')
    conn.commit()
    elapsed = time.time() - t0
    cursor.execute('SELECT COUNT(*) FROM `用户余额表`')
    print(f'    导入完成，共 {cursor.fetchone()[0]:,} 行，耗时 {elapsed:.1f}s')

    # ----- 用户画像表 -----
    print('  导入 用户画像表.csv...')
    t0 = time.time()
    cursor.execute(f'''
        LOAD DATA INFILE '{MYSQL_UPLOAD_DIR}用户画像表.csv'
        INTO TABLE `用户画像表`
        FIELDS TERMINATED BY ',' OPTIONALLY ENCLOSED BY '"'
        LINES TERMINATED BY '\\r\\n'
        IGNORE 1 ROWS
    ''')
    conn.commit()
    elapsed = time.time() - t0
    cursor.execute('SELECT COUNT(*) FROM `用户画像表`')
    print(f'    导入完成，共 {cursor.fetchone()[0]:,} 行，耗时 {elapsed:.1f}s')

    # ----- 货币基金日收益率表 -----
    print('  导入 货币基金日收益率表.csv...')
    t0 = time.time()
    cursor.execute(f'''
        LOAD DATA INFILE '{MYSQL_UPLOAD_DIR}货币基金日收益率表.csv'
        INTO TABLE `收益率表`
        FIELDS TERMINATED BY ',' OPTIONALLY ENCLOSED BY '"'
        LINES TERMINATED BY '\\r\\n'
        IGNORE 1 ROWS
        (@raw_date, `万份收益`, `七日年化收益率`)
        SET `日期` = STR_TO_DATE(@raw_date, '%Y%m%d')
    ''')
    conn.commit()
    elapsed = time.time() - t0
    cursor.execute('SELECT COUNT(*) FROM `收益率表`')
    print(f'    导入完成，共 {cursor.fetchone()[0]:,} 行，耗时 {elapsed:.1f}s')

    # ----- 银行间拆借利率表 -----
    print('  导入 银行间拆借利率表.csv...')
    t0 = time.time()
    cursor.execute(f'''
        LOAD DATA INFILE '{MYSQL_UPLOAD_DIR}银行间拆借利率表.csv'
        INTO TABLE `拆借利率表`
        FIELDS TERMINATED BY ',' OPTIONALLY ENCLOSED BY '"'
        LINES TERMINATED BY '\\r\\n'
        IGNORE 1 ROWS
        (@raw_date, `隔夜利率`, `一周利率`, `两周利率`, `一月利率`,
         `三月利率`, `六月利率`, `九月利率`, `一年利率`)
        SET `日期` = STR_TO_DATE(@raw_date, '%Y%m%d')
    ''')
    conn.commit()
    elapsed = time.time() - t0
    cursor.execute('SELECT COUNT(*) FROM `拆借利率表`')
    print(f'    导入完成，共 {cursor.fetchone()[0]:,} 行，耗时 {elapsed:.1f}s')

    conn.close()
    print()


def validate_data():
    """数据验证：检查各表的行数和日期范围"""
    print('=' * 60)
    print('Step 4/4: 数据验证')
    print('=' * 60)

    conn = get_connection(use_db=True)
    cursor = conn.cursor()

    # 各表行数
    print('  --- 各表行数 ---')
    cursor.execute('''
        SELECT '用户余额表' AS tbl, COUNT(*) AS cnt FROM `用户余额表`
        UNION ALL SELECT '用户画像表', COUNT(*) FROM `用户画像表`
        UNION ALL SELECT '收益率表', COUNT(*) FROM `收益率表`
        UNION ALL SELECT '拆借利率表', COUNT(*) FROM `拆借利率表`
        UNION ALL SELECT '日历表', COUNT(*) FROM `日历表`
        UNION ALL SELECT '节假日表', COUNT(*) FROM `节假日表`
    ''')
    for tbl, cnt in cursor.fetchall():
        print(f'  {tbl:20s}: {cnt:>12,}')

    # 用户余额表 日期范围
    cursor.execute('SELECT MIN(`报告日期`), MAX(`报告日期`) FROM `用户余额表`')
    d_min, d_max = cursor.fetchone()
    print(f'\n  用户余额表 日期范围: {d_min} ~ {d_max}')

    # 用户余额表 唯一用户数
    cursor.execute('SELECT COUNT(DISTINCT `用户ID`) FROM `用户余额表`')
    n_users = cursor.fetchone()[0]
    print(f'  唯一用户数: {n_users:,}')

    # 各外部表的日期范围
    for tbl in ['收益率表', '拆借利率表']:
        cursor.execute(f'SELECT MIN(`日期`), MAX(`日期`) FROM `{tbl}`')
        d_min, d_max = cursor.fetchone()
        print(f'  {tbl} 日期范围: {d_min} ~ {d_max}')

    conn.close()
    print('\n  [验证通过] 所有数据已成功入库！\n')


def main():
    """主流程"""
    print('\n' + '=' * 60)
    print('  资金流入流出预测 — Step 1: MySQL 数据入库')
    print('=' * 60 + '\n')

    # 复制 CSV 到 MySQL 上传目录（secure_file_priv 要求）
    copy_csv_files()

    create_database_and_tables()
    load_csv_data()
    validate_data()

    print('=' * 60)
    print('  Step 1 完成！现在可以进行 Step 2（天级聚合）。')
    print('=' * 60)


if __name__ == '__main__':
    main()
