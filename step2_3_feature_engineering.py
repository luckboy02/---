# -*- coding: utf-8 -*-
"""
============================================================
Step 2+3: 天级聚合 + 特征工程（SQL 核心）
 - 天级聚合表 天级聚合表
 - 日历特征 日历特征表
 - 节假日特征 节假日特征表
 - 滞后特征 滞后特征表
 - 滑窗统计特征 滑窗统计特征表
 - 同周几历史特征 同周几特征表
 - 外部市场特征（收益率+Shibor） 市场特征表
 - 用户行为结构特征 行为结构特征表
 - 趋势与变化率特征 趋势特征表
 - 最终训练特征宽表 训练特征表
============================================================
"""

import pymysql
import time

MYSQL_CONFIG = {
    'host': 'localhost', 'port': 3306,
    'user': 'root', 'password': 'wq010205',
    'database': '资金流入流出', 'charset': 'utf8mb4',
}


def execute_sql(title, sql):
    """执行 SQL，带耗时打印"""
    conn = pymysql.connect(**MYSQL_CONFIG)
    cursor = conn.cursor()
    t0 = time.time()
    # 分句执行（分号分隔的多条语句）
    for stmt in sql.strip().split(';'):
        stmt = stmt.strip()
        if not stmt:
            continue
        cursor.execute(stmt)
    conn.commit()
    elapsed = time.time() - t0
    cursor.close()
    conn.close()
    print(f'  {title} ... 完成 ({elapsed:.1f}s)')


# =====================================================
# Step 2: 天级聚合
# =====================================================
DAILY_AGG_SQL = """
DROP TABLE IF EXISTS `天级聚合表`;
CREATE TABLE `天级聚合表` AS
SELECT
    c.`报告日期`,
    COALESCE(SUM(b.`总申购金额`), 0)  AS `总申购金额`,
    COALESCE(SUM(b.`总赎回金额`), 0)  AS `总赎回金额`,
    COALESCE(SUM(b.`直接申购金额`), 0) AS `直接申购小计`,
    COALESCE(SUM(b.`余额申购金额`), 0) AS `余额申购小计`,
    COALESCE(SUM(b.`银行卡申购金额`), 0) AS `银行卡申购小计`,
    COALESCE(SUM(b.`消费金额`), 0)     AS `消费小计`,
    COALESCE(SUM(b.`转账金额`), 0)     AS `转账小计`,
    COALESCE(SUM(b.`转入余额宝金额`), 0) AS `转入余额宝小计`,
    COALESCE(SUM(b.`转出到银行卡金额`), 0) AS `转出到银行卡小计`,
    COALESCE(SUM(b.`分享金额`), 0)     AS `分享金额合计`,
    COALESCE(SUM(b.`类别1`), 0)        AS `类别1合计`,
    COALESCE(SUM(b.`类别2`), 0)        AS `类别2合计`,
    COALESCE(SUM(b.`类别3`), 0)        AS `类别3合计`,
    COALESCE(SUM(b.`类别4`), 0)        AS `类别4合计`,
    COUNT(DISTINCT b.`用户ID`)         AS `活跃用户数`,
    COUNT(DISTINCT CASE WHEN b.`总申购金额` > 0
                        THEN b.`用户ID` END) AS `申购用户数`,
    COUNT(DISTINCT CASE WHEN b.`总赎回金额` > 0
                        THEN b.`用户ID` END) AS `赎回用户数`,
    COALESCE(SUM(b.`今日余额`), 0)     AS `总余额`
FROM `日历表` c
LEFT JOIN `用户余额表` b ON c.`报告日期` = b.`报告日期`
WHERE c.`报告日期` <= '2014-08-31'
GROUP BY c.`报告日期`
ORDER BY c.`报告日期`;
ALTER TABLE `天级聚合表` ADD PRIMARY KEY (`报告日期`)
"""

# =====================================================
# Step 3.1: 日历特征
# =====================================================
FEAT_CALENDAR_SQL = """
DROP TABLE IF EXISTS `日历特征表`;
CREATE TABLE `日历特征表` AS
SELECT
    `报告日期`,
    DAYOFWEEK(`报告日期`)  AS `星期几`,
    CASE WHEN DAYOFWEEK(`报告日期`) IN (1, 7)
         THEN 1 ELSE 0 END AS `是否周末`,
    DAY(`报告日期`)        AS `月中第几天`,
    MONTH(`报告日期`)      AS `月份`,
    QUARTER(`报告日期`)    AS `季度`,
    CEIL(DAY(`报告日期`) / 7.0) AS `月中第几周`,
    CASE WHEN DAY(`报告日期`) <= 3
         THEN 1 ELSE 0 END AS `是否月初`,
    CASE WHEN DAY(`报告日期`) >= DAY(LAST_DAY(`报告日期`)) - 2
         THEN 1 ELSE 0 END AS `是否月末`,
    CASE WHEN MONTH(`报告日期`) IN (3,6,9,12)
          AND DAY(`报告日期`) >= DAY(LAST_DAY(`报告日期`)) - 2
         THEN 1 ELSE 0 END AS `是否季末`,
    CASE WHEN DAY(`报告日期`) IN (10,15,25)
         THEN 1 ELSE 0 END AS `是否发薪日`
FROM `日历表`;
ALTER TABLE `日历特征表` ADD PRIMARY KEY (`报告日期`)
"""

# =====================================================
# Step 3.2: 节假日特征
# =====================================================
FEAT_HOLIDAY_SQL = """
DROP TABLE IF EXISTS `节假日特征表`;
CREATE TABLE `节假日特征表` AS
SELECT
    c.`报告日期`,
    CASE WHEN h.`节假日日期` IS NOT NULL THEN 1 ELSE 0 END AS `是否节假日`,
    (SELECT MIN(DATEDIFF(h2.`节假日日期`, c.`报告日期`))
     FROM `节假日表` h2
     WHERE h2.`节假日日期` >= c.`报告日期`)  AS `距下一节假日天数`,
    (SELECT MIN(DATEDIFF(c.`报告日期`, h3.`节假日日期`))
     FROM `节假日表` h3
     WHERE h3.`节假日日期` <= c.`报告日期`)  AS `距上一节假日天数`
FROM `日历表` c
LEFT JOIN `节假日表` h ON c.`报告日期` = h.`节假日日期`;
ALTER TABLE `节假日特征表` ADD PRIMARY KEY (`报告日期`)
"""

# =====================================================
# Step 3.3: 滞后特征
# =====================================================
FEAT_LAG_SQL = """
DROP TABLE IF EXISTS `滞后特征表`;
CREATE TABLE `滞后特征表` AS
SELECT
    `报告日期`,
    LAG(`总申购金额`, 1)  OVER w AS `申购滞后1天`,
    LAG(`总申购金额`, 2)  OVER w AS `申购滞后2天`,
    LAG(`总申购金额`, 3)  OVER w AS `申购滞后3天`,
    LAG(`总申购金额`, 7)  OVER w AS `申购滞后7天`,
    LAG(`总申购金额`, 14) OVER w AS `申购滞后14天`,
    LAG(`总申购金额`, 21) OVER w AS `申购滞后21天`,
    LAG(`总申购金额`, 28) OVER w AS `申购滞后28天`,
    LAG(`总申购金额`, 30) OVER w AS `申购滞后30天`,
    LAG(`总赎回金额`, 1)  OVER w AS `赎回滞后1天`,
    LAG(`总赎回金额`, 2)  OVER w AS `赎回滞后2天`,
    LAG(`总赎回金额`, 3)  OVER w AS `赎回滞后3天`,
    LAG(`总赎回金额`, 7)  OVER w AS `赎回滞后7天`,
    LAG(`总赎回金额`, 14) OVER w AS `赎回滞后14天`,
    LAG(`总赎回金额`, 21) OVER w AS `赎回滞后21天`,
    LAG(`总赎回金额`, 28) OVER w AS `赎回滞后28天`,
    LAG(`总赎回金额`, 30) OVER w AS `赎回滞后30天`
FROM `天级聚合表`
WINDOW w AS (ORDER BY `报告日期`);
ALTER TABLE `滞后特征表` ADD PRIMARY KEY (`报告日期`)
"""

# =====================================================
# Step 3.4: 滑窗统计特征
# =====================================================
FEAT_ROLLING_SQL = """
DROP TABLE IF EXISTS `滑窗统计特征表`;
CREATE TABLE `滑窗统计特征表` AS
SELECT
    `报告日期`,
    AVG(`总申购金额`) OVER (ORDER BY `报告日期`
        ROWS BETWEEN 7 PRECEDING AND 1 PRECEDING)  AS `申购7日滚动均值`,
    AVG(`总申购金额`) OVER (ORDER BY `报告日期`
        ROWS BETWEEN 14 PRECEDING AND 1 PRECEDING) AS `申购14日滚动均值`,
    AVG(`总申购金额`) OVER (ORDER BY `报告日期`
        ROWS BETWEEN 30 PRECEDING AND 1 PRECEDING) AS `申购30日滚动均值`,
    STDDEV(`总申购金额`) OVER (ORDER BY `报告日期`
        ROWS BETWEEN 7 PRECEDING AND 1 PRECEDING)  AS `申购7日滚动标准差`,
    STDDEV(`总申购金额`) OVER (ORDER BY `报告日期`
        ROWS BETWEEN 30 PRECEDING AND 1 PRECEDING) AS `申购30日滚动标准差`,
    MAX(`总申购金额`) OVER (ORDER BY `报告日期`
        ROWS BETWEEN 7 PRECEDING AND 1 PRECEDING)  AS `申购7日滚动最大值`,
    MIN(`总申购金额`) OVER (ORDER BY `报告日期`
        ROWS BETWEEN 7 PRECEDING AND 1 PRECEDING)  AS `申购7日滚动最小值`,
    AVG(`总赎回金额`) OVER (ORDER BY `报告日期`
        ROWS BETWEEN 7 PRECEDING AND 1 PRECEDING)  AS `赎回7日滚动均值`,
    AVG(`总赎回金额`) OVER (ORDER BY `报告日期`
        ROWS BETWEEN 14 PRECEDING AND 1 PRECEDING) AS `赎回14日滚动均值`,
    AVG(`总赎回金额`) OVER (ORDER BY `报告日期`
        ROWS BETWEEN 30 PRECEDING AND 1 PRECEDING) AS `赎回30日滚动均值`,
    STDDEV(`总赎回金额`) OVER (ORDER BY `报告日期`
        ROWS BETWEEN 7 PRECEDING AND 1 PRECEDING)  AS `赎回7日滚动标准差`,
    STDDEV(`总赎回金额`) OVER (ORDER BY `报告日期`
        ROWS BETWEEN 30 PRECEDING AND 1 PRECEDING) AS `赎回30日滚动标准差`,
    MAX(`总赎回金额`) OVER (ORDER BY `报告日期`
        ROWS BETWEEN 7 PRECEDING AND 1 PRECEDING)  AS `赎回7日滚动最大值`,
    MIN(`总赎回金额`) OVER (ORDER BY `报告日期`
        ROWS BETWEEN 7 PRECEDING AND 1 PRECEDING)  AS `赎回7日滚动最小值`
FROM `天级聚合表`;
ALTER TABLE `滑窗统计特征表` ADD PRIMARY KEY (`报告日期`)
"""

# =====================================================
# Step 3.5: 同周几历史特征
# =====================================================
FEAT_SAME_WEEKDAY_SQL = """
DROP TABLE IF EXISTS `同周几特征表`;
CREATE TABLE `同周几特征表` AS
SELECT
    a.`报告日期`,
    b1.`总申购金额` AS `申购同周几1周前`,
    b1.`总赎回金额` AS `赎回同周几1周前`,
    b2.`总申购金额` AS `申购同周几2周前`,
    b2.`总赎回金额` AS `赎回同周几2周前`,
    b3.`总申购金额` AS `申购同周几3周前`,
    b3.`总赎回金额` AS `赎回同周几3周前`,
    b4.`总申购金额` AS `申购同周几4周前`,
    b4.`总赎回金额` AS `赎回同周几4周前`,
    (COALESCE(b1.`总申购金额`,0) + COALESCE(b2.`总申购金额`,0)
   + COALESCE(b3.`总申购金额`,0) + COALESCE(b4.`总申购金额`,0))
   / NULLIF(
       (b1.`总申购金额` IS NOT NULL) + (b2.`总申购金额` IS NOT NULL)
     + (b3.`总申购金额` IS NOT NULL) + (b4.`总申购金额` IS NOT NULL), 0)
    AS `申购同周几4周均值`,
    (COALESCE(b1.`总赎回金额`,0) + COALESCE(b2.`总赎回金额`,0)
   + COALESCE(b3.`总赎回金额`,0) + COALESCE(b4.`总赎回金额`,0))
   / NULLIF(
       (b1.`总赎回金额` IS NOT NULL) + (b2.`总赎回金额` IS NOT NULL)
     + (b3.`总赎回金额` IS NOT NULL) + (b4.`总赎回金额` IS NOT NULL), 0)
    AS `赎回同周几4周均值`
FROM `天级聚合表` a
LEFT JOIN `天级聚合表` b1 ON b1.`报告日期` = DATE_SUB(a.`报告日期`, INTERVAL  7 DAY)
LEFT JOIN `天级聚合表` b2 ON b2.`报告日期` = DATE_SUB(a.`报告日期`, INTERVAL 14 DAY)
LEFT JOIN `天级聚合表` b3 ON b3.`报告日期` = DATE_SUB(a.`报告日期`, INTERVAL 21 DAY)
LEFT JOIN `天级聚合表` b4 ON b4.`报告日期` = DATE_SUB(a.`报告日期`, INTERVAL 28 DAY);
ALTER TABLE `同周几特征表` ADD PRIMARY KEY (`报告日期`)
"""

# =====================================================
# Step 3.6: 外部市场特征（收益率 + Shibor，前向填充缺失值）
# =====================================================
FEAT_MARKET_SQL = """
DROP TABLE IF EXISTS `市场特征表`;
CREATE TABLE `市场特征表` AS
SELECT
    c.`报告日期`,
    COALESCE(i.`万份收益`,
        (SELECT i2.`万份收益` FROM `收益率表` i2
         WHERE i2.`日期` <= c.`报告日期`
         ORDER BY i2.`日期` DESC LIMIT 1))      AS `万份收益`,
    COALESCE(i.`七日年化收益率`,
        (SELECT i3.`七日年化收益率` FROM `收益率表` i3
         WHERE i3.`日期` <= c.`报告日期`
         ORDER BY i3.`日期` DESC LIMIT 1))      AS `七日年化收益率`,
    COALESCE(s.`隔夜利率`,
        (SELECT s2.`隔夜利率` FROM `拆借利率表` s2
         WHERE s2.`日期` <= c.`报告日期`
         ORDER BY s2.`日期` DESC LIMIT 1))      AS `隔夜拆借利率`,
    COALESCE(s.`一周利率`,
        (SELECT s3.`一周利率` FROM `拆借利率表` s3
         WHERE s3.`日期` <= c.`报告日期`
         ORDER BY s3.`日期` DESC LIMIT 1))      AS `一周拆借利率`,
    COALESCE(s.`一月利率`,
        (SELECT s4.`一月利率` FROM `拆借利率表` s4
         WHERE s4.`日期` <= c.`报告日期`
         ORDER BY s4.`日期` DESC LIMIT 1))      AS `一月拆借利率`,
    COALESCE(s.`三月利率`,
        (SELECT s5.`三月利率` FROM `拆借利率表` s5
         WHERE s5.`日期` <= c.`报告日期`
         ORDER BY s5.`日期` DESC LIMIT 1))      AS `三月拆借利率`
FROM `日历表` c
LEFT JOIN `收益率表` i ON c.`报告日期` = i.`日期`
LEFT JOIN `拆借利率表` s ON c.`报告日期` = s.`日期`;
ALTER TABLE `市场特征表` ADD PRIMARY KEY (`报告日期`)
"""

# =====================================================
# Step 3.7: 用户行为结构特征
# =====================================================
FEAT_STRUCTURE_SQL = """
DROP TABLE IF EXISTS `行为结构特征表`;
CREATE TABLE `行为结构特征表` AS
SELECT
    `报告日期`,
    CASE WHEN `总申购金额` > 0
         THEN `直接申购小计` / `总申购金额` ELSE 0 END AS `直接申购比例`,
    CASE WHEN `总申购金额` > 0
         THEN `银行卡申购小计` / `总申购金额` ELSE 0 END AS `银行卡申购比例`,
    CASE WHEN `总赎回金额` > 0
         THEN `消费小计` / `总赎回金额` ELSE 0 END     AS `消费比例`,
    CASE WHEN `总赎回金额` > 0
         THEN `转出到银行卡小计` / `总赎回金额` ELSE 0 END AS `转出到卡比例`,
    CASE WHEN `总赎回金额` > 0
         THEN `转入余额宝小计` / `总赎回金额` ELSE 0 END AS `转入余额宝比例`,
    CASE WHEN `申购用户数` > 0
         THEN `总申购金额` / `申购用户数` ELSE 0 END AS `人均申购金额`,
    CASE WHEN `赎回用户数` > 0
         THEN `总赎回金额` / `赎回用户数` ELSE 0 END AS `人均赎回金额`,
    CASE WHEN `活跃用户数` > 0
         THEN `申购用户数` / `活跃用户数` ELSE 0 END AS `申购用户比例`,
    CASE WHEN `活跃用户数` > 0
         THEN `赎回用户数` / `活跃用户数` ELSE 0 END AS `赎回用户比例`,
    `类别1合计`, `类别2合计`, `类别3合计`, `类别4合计`
FROM `天级聚合表`;
ALTER TABLE `行为结构特征表` ADD PRIMARY KEY (`报告日期`)
"""

# =====================================================
# Step 3.8: 趋势与变化率特征
# =====================================================
FEAT_TREND_SQL = """
DROP TABLE IF EXISTS `趋势特征表`;
CREATE TABLE `趋势特征表` AS
SELECT
    `报告日期`,
    CASE WHEN LAG(`总申购金额`,1) OVER w > 0
         THEN (`总申购金额` - LAG(`总申购金额`,1) OVER w)
              / LAG(`总申购金额`,1) OVER w
         ELSE 0 END AS `申购日变化率`,
    CASE WHEN LAG(`总申购金额`,7) OVER w > 0
         THEN (`总申购金额` - LAG(`总申购金额`,7) OVER w)
              / LAG(`总申购金额`,7) OVER w
         ELSE 0 END AS `申购周变化率`,
    CASE WHEN LAG(`总赎回金额`,1) OVER w > 0
         THEN (`总赎回金额` - LAG(`总赎回金额`,1) OVER w)
              / LAG(`总赎回金额`,1) OVER w
         ELSE 0 END AS `赎回日变化率`,
    CASE WHEN LAG(`总赎回金额`,7) OVER w > 0
         THEN (`总赎回金额` - LAG(`总赎回金额`,7) OVER w)
              / LAG(`总赎回金额`,7) OVER w
         ELSE 0 END AS `赎回周变化率`,
    CASE WHEN `总赎回金额` > 0
         THEN `总申购金额` / `总赎回金额` ELSE 0 END AS `申购赎回比`
FROM `天级聚合表`
WINDOW w AS (ORDER BY `报告日期`);
ALTER TABLE `趋势特征表` ADD PRIMARY KEY (`报告日期`)
"""

# =====================================================
# Step 3.9: 最终训练特征宽表
# =====================================================
TRAIN_FEATURES_SQL = """
DROP TABLE IF EXISTS `训练特征表`;
CREATE TABLE `训练特征表` AS
SELECT
    d.`报告日期`,
    d.`总申购金额`,
    d.`总赎回金额`,
    cal.`星期几`, cal.`是否周末`, cal.`月中第几天`, cal.`月份`, cal.`季度`,
    cal.`月中第几周`, cal.`是否月初`, cal.`是否月末`,
    cal.`是否季末`, cal.`是否发薪日`,
    hol.`是否节假日`, hol.`距下一节假日天数`, hol.`距上一节假日天数`,
    lg.`申购滞后1天`, lg.`申购滞后2天`, lg.`申购滞后3天`, lg.`申购滞后7天`, lg.`申购滞后14天`,
    lg.`申购滞后21天`, lg.`申购滞后28天`, lg.`申购滞后30天`,
    lg.`赎回滞后1天`, lg.`赎回滞后2天`, lg.`赎回滞后3天`, lg.`赎回滞后7天`, lg.`赎回滞后14天`,
    lg.`赎回滞后21天`, lg.`赎回滞后28天`, lg.`赎回滞后30天`,
    rl.`申购7日滚动均值`, rl.`申购14日滚动均值`, rl.`申购30日滚动均值`,
    rl.`申购7日滚动标准差`, rl.`申购30日滚动标准差`, rl.`申购7日滚动最大值`, rl.`申购7日滚动最小值`,
    rl.`赎回7日滚动均值`, rl.`赎回14日滚动均值`, rl.`赎回30日滚动均值`,
    rl.`赎回7日滚动标准差`, rl.`赎回30日滚动标准差`, rl.`赎回7日滚动最大值`, rl.`赎回7日滚动最小值`,
    sw.`申购同周几1周前`, sw.`申购同周几2周前`, sw.`申购同周几3周前`, sw.`申购同周几4周前`,
    sw.`申购同周几4周均值`,
    sw.`赎回同周几1周前`, sw.`赎回同周几2周前`, sw.`赎回同周几3周前`, sw.`赎回同周几4周前`,
    sw.`赎回同周几4周均值`,
    mk.`万份收益`, mk.`七日年化收益率`,
    mk.`隔夜拆借利率`, mk.`一周拆借利率`, mk.`一月拆借利率`, mk.`三月拆借利率`,
    st.`直接申购比例`, st.`银行卡申购比例`,
    st.`消费比例`, st.`转出到卡比例`, st.`转入余额宝比例`,
    st.`人均申购金额`, st.`人均赎回金额`,
    st.`申购用户比例`, st.`赎回用户比例`,
    st.`类别1合计`, st.`类别2合计`, st.`类别3合计`, st.`类别4合计`,
    tr.`申购日变化率`, tr.`申购周变化率`,
    tr.`赎回日变化率`, tr.`赎回周变化率`,
    tr.`申购赎回比`
FROM `天级聚合表` d
JOIN `日历特征表`       cal ON d.`报告日期` = cal.`报告日期`
JOIN `节假日特征表`     hol ON d.`报告日期` = hol.`报告日期`
LEFT JOIN `滞后特征表`       lg  ON d.`报告日期` = lg.`报告日期`
LEFT JOIN `滑窗统计特征表`   rl  ON d.`报告日期` = rl.`报告日期`
LEFT JOIN `同周几特征表`     sw  ON d.`报告日期` = sw.`报告日期`
LEFT JOIN `市场特征表`       mk  ON d.`报告日期` = mk.`报告日期`
LEFT JOIN `行为结构特征表`   st  ON d.`报告日期` = st.`报告日期`
LEFT JOIN `趋势特征表`       tr  ON d.`报告日期` = tr.`报告日期`
ORDER BY d.`报告日期`;
ALTER TABLE `训练特征表` ADD PRIMARY KEY (`报告日期`)
"""


def main():
    print('\n' + '=' * 60)
    print('  资金流入流出预测 — Step 2+3: 天级聚合 + 特征工程')
    print('=' * 60 + '\n')

    # ---- Step 2 ----
    print('[Step 2] 天级聚合')
    execute_sql('天级聚合表', DAILY_AGG_SQL)

    # ---- Step 3 ----
    print('\n[Step 3] 特征工程')

    sql_list = [
        ('日历特征表',       FEAT_CALENDAR_SQL),
        ('节假日特征表',     FEAT_HOLIDAY_SQL),
        ('滞后特征表',       FEAT_LAG_SQL),
        ('滑窗统计特征表',   FEAT_ROLLING_SQL),
        ('同周几特征表',     FEAT_SAME_WEEKDAY_SQL),
        ('市场特征表',       FEAT_MARKET_SQL),
        ('行为结构特征表',   FEAT_STRUCTURE_SQL),
        ('趋势特征表',       FEAT_TREND_SQL),
    ]
    for title, sql in sql_list:
        execute_sql(title, sql)

    # ---- 最终宽表 ----
    print('\n[汇总] 最终训练特征宽表')
    execute_sql('训练特征表', TRAIN_FEATURES_SQL)

    # ---- 验证 ----
    print('\n' + '=' * 60)
    print('  特征表验证')
    print('=' * 60)
    conn = pymysql.connect(**MYSQL_CONFIG)
    cursor = conn.cursor()

    # 行数与NULL检查
    cursor.execute("""
        SELECT COUNT(*) AS total_rows,
               SUM(CASE WHEN `申购滞后7天` IS NULL THEN 1 ELSE 0 END) AS null_lag7
        FROM `训练特征表`
    """)
    total, null_lag = cursor.fetchone()
    print(f'  训练特征表 总行数: {total}')
    print(f'  申购滞后7天 为 NULL 的行数: {null_lag} (前30天正常)')

    # 前5行预览
    cursor.execute("""
        SELECT `报告日期`, `总申购金额`, `总赎回金额`,
               `申购滞后1天`, `赎回滞后1天`, `是否周末`, `是否节假日`
        FROM `训练特征表`
        ORDER BY `报告日期`
        LIMIT 5
    """)
    print('\n  前5行预览:')
    print(f'  {"日期":>12s} {"申购":>14s} {"赎回":>14s} '
          f'{"申购滞后1天":>14s} {"赎回滞后1天":>14s} {"周末":>4s} {"假期":>4s}')
    for row in cursor.fetchall():
        print(f'  {str(row[0]):>12s} {row[1]:>14,.0f} {row[2]:>14,.0f} '
              f'{row[3] or 0:>14,.0f} {row[4] or 0:>14,.0f} '
              f'{row[5]:>4d} {row[6]:>4d}')

    # 特征列数
    cursor.execute("SELECT COUNT(*) FROM information_schema.columns "
                   "WHERE table_schema='资金流入流出' AND table_name='训练特征表'")
    n_cols = cursor.fetchone()[0]
    print(f'\n  训练特征表 特征列数: {n_cols}')

    conn.close()

    print('\n' + '=' * 60)
    print('  Step 2+3 完成！现在可以进行 Step 4（Python 建模）。')
    print('=' * 60)


if __name__ == '__main__':
    main()
