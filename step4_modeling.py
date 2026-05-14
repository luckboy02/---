# -*- coding: utf-8 -*-
"""
============================================================
Step 4: Python 建模
 - 从 训练特征表 加载数据
 - 训练/验证集划分（2014-08 = 验证）
 - LightGBM + XGBoost + Ridge 三模型训练
 - 网格搜索最优融合权重
 - 全量重训练
 - 9月递归预测（逐日推进）
 - 输出 预测结果表.csv
============================================================
"""

import pandas as pd
import numpy as np
import pymysql
import lightgbm as lgb
import xgboost as xgb
from sklearn.linear_model import Ridge
from sklearn.preprocessing import StandardScaler
import warnings
import time

warnings.filterwarnings('ignore')

# =====================================================
# 0. 配置
# =====================================================
MYSQL_CONFIG = {
    'host': 'localhost', 'port': 3306,
    'user': 'root', 'password': 'wq010205',
    'database': '资金流入流出', 'charset': 'utf8mb4',
}

OUTPUT_FILE = 'D:/Modeling code/数据分析项目/资金流入流出预测/Purchase Redemption Data/预测结果表.csv'

# 验证集分割点（模拟预测9月，用8月做验证）
VALID_START = '2014-08-01'

# 不参与建模的列
DROP_COLS = ['报告日期', '总申购金额', '总赎回金额']


# =====================================================
# 一、数据加载
# =====================================================
def load_data():
    print('=' * 60)
    print('  一、数据加载')
    print('=' * 60)
    conn = pymysql.connect(**MYSQL_CONFIG)
    df = pd.read_sql("SELECT * FROM `训练特征表` ORDER BY `报告日期`", conn)
    conn.close()
    df['报告日期'] = pd.to_datetime(df['报告日期'])
    print(f'  特征表形状: {df.shape}')
    print(f'  日期范围: {df["报告日期"].min().date()} ~ {df["报告日期"].max().date()}')
    return df


# =====================================================
# 二、特征列划分
# =====================================================
def build_feature_cols(all_cols):
    """划分申购和赎回各自的特征列，避免标签泄露"""
    # 申购特征：排除赎回专属的 lag/rolling/same_wd/change_rate
    purchase_cols = [c for c in all_cols
                     if c not in DROP_COLS
                     and not c.startswith('赎回滞后')
                     and not (c.startswith('赎回') and '滚动' in c)
                     and not c.startswith('赎回同周几')
                     and c not in ['赎回日变化率',
                                   '赎回周变化率']]

    # 赎回特征：排除申购专属的 lag/rolling/same_wd/change_rate
    redeem_cols = [c for c in all_cols
                   if c not in DROP_COLS
                   and not c.startswith('申购滞后')
                   and not (c.startswith('申购') and '滚动' in c)
                   and not c.startswith('申购同周几')
                   and c not in ['申购日变化率',
                                 '申购周变化率']]

    print(f'\n  申购特征数: {len(purchase_cols)}')
    print(f'  赎回特征数: {len(redeem_cols)}')
    return purchase_cols, redeem_cols


# =====================================================
# 三、自定义评估函数（对齐比赛指标）
# =====================================================
def relative_error(y_true, y_pred):
    """每日相对误差"""
    return np.abs(y_true - y_pred) / np.where(y_true == 0, 1, y_true)


def competition_score(y_true, y_pred):
    """
    模拟比赛评分：
    - 每天误差=0 → 10分，误差>=0.3 → 0分
    - 线性近似：score = max(0, 10 * (1 - re/0.3))
    """
    re = relative_error(y_true, y_pred)
    daily_scores = np.maximum(0, 10 * (1 - re / 0.3))
    return daily_scores.sum(), daily_scores


def full_score(y_true_p, y_pred_p, y_true_r, y_pred_r):
    """总分 = 申购*45% + 赎回*55%"""
    score_p, _ = competition_score(y_true_p, y_pred_p)
    score_r, _ = competition_score(y_true_r, y_pred_r)
    total = score_p * 0.45 + score_r * 0.55
    return total, score_p, score_r


# =====================================================
# 四、模型训练函数
# =====================================================
def train_lgb(X_train, y_train, X_valid, y_valid, label='purchase'):
    """LightGBM 训练"""
    params = {
        'objective': 'regression',
        'metric': 'mape',
        'boosting_type': 'gbdt',
        'learning_rate': 0.05,
        'num_leaves': 31,
        'max_depth': 6,
        'min_child_samples': 10,
        'subsample': 0.8,
        'colsample_bytree': 0.8,
        'reg_alpha': 0.1,
        'reg_lambda': 0.1,
        'verbose': -1,
        'n_jobs': -1,
        'seed': 42,
    }
    dtrain = lgb.Dataset(X_train, y_train)
    dvalid = lgb.Dataset(X_valid, y_valid, reference=dtrain)

    model = lgb.train(
        params, dtrain,
        num_boost_round=2000,
        valid_sets=[dvalid],
        callbacks=[
            lgb.early_stopping(100),
            lgb.log_evaluation(200),
        ],
    )
    print(f'  [LGB-{label}] best_iteration = {model.best_iteration}')
    return model


def train_xgb(X_train, y_train, X_valid, y_valid, label='purchase'):
    """XGBoost 训练"""
    params = {
        'objective': 'reg:squarederror',
        'eval_metric': 'mape',
        'learning_rate': 0.05,
        'max_depth': 6,
        'min_child_weight': 10,
        'subsample': 0.8,
        'colsample_bytree': 0.8,
        'reg_alpha': 0.1,
        'reg_lambda': 1.0,
        'seed': 42,
        'verbosity': 0,
    }
    dtrain = xgb.DMatrix(X_train, y_train)
    dvalid = xgb.DMatrix(X_valid, y_valid)

    model = xgb.train(
        params, dtrain,
        num_boost_round=2000,
        evals=[(dvalid, 'valid')],
        early_stopping_rounds=100,
        verbose_eval=200,
    )
    print(f'  [XGB-{label}] best_iteration = {model.best_iteration}')
    return model


def train_ridge(X_train, y_train, label='purchase'):
    """Ridge 回归（需标准化）"""
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X_train.fillna(0))
    model = Ridge(alpha=100.0)
    model.fit(X_scaled, y_train)
    print(f'  [Ridge-{label}] R2(train) = {model.score(X_scaled, y_train):.4f}')
    return model, scaler


# =====================================================
# 五、网格搜索最优融合权重
# =====================================================
def grid_search_weights(y_valid_p, y_valid_r, preds_p, preds_r):
    """
    对申购和赎回分别搜索最优融合权重。
    preds_p: dict {'lgb': array, 'xgb': array, 'ridge': array}
    """
    best_total = -1
    best_w = None

    for w1 in np.arange(0.1, 0.8, 0.1):
        for w2 in np.arange(0.1, 0.9 - w1, 0.1):
            w3 = round(1.0 - w1 - w2, 2)
            if w3 < 0:
                continue
            fused_p = w1 * preds_p['lgb'] + w2 * preds_p['xgb'] + w3 * preds_p['ridge']
            fused_r = w1 * preds_r['lgb'] + w2 * preds_r['xgb'] + w3 * preds_r['ridge']
            total, sp, sr = full_score(
                y_valid_p.values, fused_p,
                y_valid_r.values, fused_r,
            )
            if total > best_total:
                best_total = total
                best_w = (w1, w2, w3)
                best_sp = sp
                best_sr = sr

    print(f'\n  最优融合权重: LGB={best_w[0]:.1f}, XGB={best_w[1]:.1f}, Ridge={best_w[2]:.1f}')
    print(f'  验证集总分: {best_total:.2f} (申购={best_sp:.2f}, 赎回={best_sr:.2f})')
    return best_w


# =====================================================
# 六、9月递归预测
# =====================================================
def build_calendar_features(dt):
    """为给定日期构造日历+节假日特征"""
    holidays_sep = {6, 7, 8}  # 2014年9月6-8日 中秋
    mysql_dow = (dt.isoweekday() % 7) + 1  # 转为 MySQL DAYOFWEEK: 1=Sun
    dom = dt.day
    last_day = pd.Timestamp(dt.year, dt.month, 1) + pd.offsets.MonthEnd(0)
    last_dom = last_day.day
    return {
        '星期几': mysql_dow,
        '是否周末': 1 if mysql_dow in (1, 7) else 0,
        '月中第几天': dom,
        '月份': dt.month,
        '季度': (dt.month - 1) // 3 + 1,
        '月中第几周': int(np.ceil(dom / 7)),
        '是否月初': 1 if dom <= 3 else 0,
        '是否月末': 1 if dom >= last_dom - 2 else 0,
        '是否季末': 1 if dt.month in (3, 6, 9, 12) and dom >= last_dom - 2 else 0,
        '是否发薪日': 1 if dom in (10, 15, 25) else 0,
        '是否节假日': 1 if dom in holidays_sep else 0,
        '距下一节假日天数': min(d - dom for d in holidays_sep if d >= dom)
                                if any(d >= dom for d in holidays_sep) else 30,
        '距上一节假日天数': min(dom - d for d in holidays_sep if d <= dom)
                                   if any(d <= dom for d in holidays_sep) else 30,
    }


def recursive_predict(df_clean, purchase_cols, redeem_cols,
                      best_w, models_p, models_r):
    """
    对2014年9月进行递归预测。
    models_p/models_r 是 dict，包含 'lgb','xgb','ridge' 模型和 scaler。
    """
    print('\n' + '=' * 60)
    print('  六、9月递归预测')
    print('=' * 60)

    # 历史时序（用于 lag/rolling 计算）—— 仅保留 purchase 和 redeem 两列
    hist = df_clean[['报告日期', '总申购金额', '总赎回金额']].copy()
    hist = hist.set_index('报告日期').sort_index()

    # 最后一天的市场特征 / 结构特征（9月向前沿用）
    last_row = df_clean.iloc[-1]
    last_market = last_row[[
        '万份收益', '七日年化收益率', '隔夜拆借利率',
        '一周拆借利率', '一月拆借利率', '三月拆借利率',
    ]].to_dict()
    last_structure = last_row[[
        '直接申购比例', '银行卡申购比例',
        '消费比例', '转出到卡比例', '转入余额宝比例',
        '人均申购金额', '人均赎回金额',
        '申购用户比例', '赎回用户比例',
        '类别1合计', '类别2合计', '类别3合计', '类别4合计',
    ]].to_dict()

    pred_dates = pd.date_range('2014-09-01', '2014-09-30')
    results = []

    for dt in pred_dates:
        row = {}

        # 1) 日历 + 节假日
        row.update(build_calendar_features(dt))

        # 2) 滞后特征
        for lag_days, suffix in [(1, '1天'), (2, '2天'), (3, '3天'), (7, '7天'),
                                  (14, '14天'), (21, '21天'), (28, '28天'), (30, '30天')]:
            lag_dt = dt - pd.Timedelta(days=lag_days)
            if lag_dt in hist.index:
                row[f'申购滞后{suffix}'] = hist.loc[lag_dt, '总申购金额']
                row[f'赎回滞后{suffix}'] = hist.loc[lag_dt, '总赎回金额']
            else:
                row[f'申购滞后{suffix}'] = 0
                row[f'赎回滞后{suffix}'] = 0

        # 3) 滑窗统计
        for window, name in [(7, '7日'), (14, '14日'), (30, '30日')]:
            window_dates = pd.date_range(dt - pd.Timedelta(days=window),
                                          dt - pd.Timedelta(days=1))
            p_vals = [hist.loc[d, '总申购金额'] for d in window_dates
                      if d in hist.index]
            r_vals = [hist.loc[d, '总赎回金额'] for d in window_dates
                      if d in hist.index]
            row[f'申购{name}滚动均值'] = np.mean(p_vals) if p_vals else 0
            row[f'赎回{name}滚动均值'] = np.mean(r_vals) if r_vals else 0
            if name == '7日':
                row['申购7日滚动标准差'] = np.std(p_vals) if len(p_vals) > 1 else 0
                row['赎回7日滚动标准差'] = np.std(r_vals) if len(r_vals) > 1 else 0
                row['申购7日滚动最大值'] = max(p_vals) if p_vals else 0
                row['申购7日滚动最小值'] = min(p_vals) if p_vals else 0
                row['赎回7日滚动最大值'] = max(r_vals) if r_vals else 0
                row['赎回7日滚动最小值'] = min(r_vals) if r_vals else 0
            if name == '30日':
                row['申购30日滚动标准差'] = np.std(p_vals) if len(p_vals) > 1 else 0
                row['赎回30日滚动标准差'] = np.std(r_vals) if len(r_vals) > 1 else 0

        # 4) 同周几特征
        for wk, suffix in [(1, '1周前'), (2, '2周前'), (3, '3周前'), (4, '4周前')]:
            wd_dt = dt - pd.Timedelta(weeks=wk)
            if wd_dt in hist.index:
                row[f'申购同周几{suffix}'] = hist.loc[wd_dt, '总申购金额']
                row[f'赎回同周几{suffix}'] = hist.loc[wd_dt, '总赎回金额']
            else:
                row[f'申购同周几{suffix}'] = 0
                row[f'赎回同周几{suffix}'] = 0
        p_wd_vals = [row[f'申购同周几{s}'] for s in ['1周前', '2周前', '3周前', '4周前']
                     if row[f'申购同周几{s}'] > 0]
        r_wd_vals = [row[f'赎回同周几{s}'] for s in ['1周前', '2周前', '3周前', '4周前']
                     if row[f'赎回同周几{s}'] > 0]
        row['申购同周几4周均值'] = np.mean(p_wd_vals) if p_wd_vals else 0
        row['赎回同周几4周均值'] = np.mean(r_wd_vals) if r_wd_vals else 0

        # 5) 市场特征（carry forward）
        row.update(last_market)

        # 6) 结构特征（carry forward）
        row.update(last_structure)

        # 7) 趋势特征
        yesterday = dt - pd.Timedelta(days=1)
        last_week = dt - pd.Timedelta(days=7)
        yp = hist.loc[yesterday, '总申购金额'] if yesterday in hist.index else 0
        yr = hist.loc[yesterday, '总赎回金额'] if yesterday in hist.index else 0
        wp = hist.loc[last_week, '总申购金额'] if last_week in hist.index else 0
        wr = hist.loc[last_week, '总赎回金额'] if last_week in hist.index else 0
        row['申购日变化率'] = (yp - row.get('申购滞后2天', 0)) / max(row.get('申购滞后2天', 1), 1)
        row['申购周变化率'] = (yp - wp) / max(wp, 1)
        row['赎回日变化率'] = (yr - row.get('赎回滞后2天', 0)) / max(row.get('赎回滞后2天', 1), 1)
        row['赎回周变化率'] = (yr - wr) / max(wr, 1)
        row['申购赎回比'] = yp / max(yr, 1)

        # ----- 预测 -----
        row_p = pd.DataFrame([{k: row[k] for k in purchase_cols}]).fillna(0)
        row_r = pd.DataFrame([{k: row[k] for k in redeem_cols}]).fillna(0)

        # LightGBM
        p_lgb = models_p['lgb'].predict(row_p)[0]
        r_lgb = models_r['lgb'].predict(row_r)[0]
        # XGBoost
        p_xgb = models_p['xgb'].predict(xgb.DMatrix(row_p))[0]
        r_xgb = models_r['xgb'].predict(xgb.DMatrix(row_r))[0]
        # Ridge
        p_ridge = models_p['ridge'].predict(
            models_p['scaler'].transform(row_p))[0]
        r_ridge = models_r['ridge'].predict(
            models_r['scaler'].transform(row_r))[0]

        # 加权融合
        w1, w2, w3 = best_w
        pred_purchase = max(0, w1 * p_lgb + w2 * p_xgb + w3 * p_ridge)
        pred_redeem = max(0, w1 * r_lgb + w2 * r_xgb + w3 * r_ridge)

        # 更新历史（递归关键步骤）
        hist.loc[dt] = [pred_purchase, pred_redeem]

        results.append({
            '报告日期': dt.strftime('%Y%m%d'),
            '申购': int(round(pred_purchase)),
            '赎回': int(round(pred_redeem)),
        })

        print(f"  {dt.strftime('%Y-%m-%d')} | "
              f"申购={int(pred_purchase):>12,} | "
              f"赎回={int(pred_redeem):>12,}")

    return pd.DataFrame(results)


# =====================================================
# 主流程
# =====================================================
def main():
    print('\n' + '=' * 60)
    print('  资金流入流出预测 — Step 4: Python 建模')
    print('=' * 60)

    # ---- 加载 ----
    df = load_data()
    purchase_cols, redeem_cols = build_feature_cols(df.columns.tolist())

    # ---- 训练/验证集划分 ----
    # 去掉前30天（lag不完整），以2014-08为验证集
    df_clean = df[df['报告日期'] >= '2013-08-01'].copy()
    train_mask = df_clean['报告日期'] < VALID_START
    valid_mask = df_clean['报告日期'] >= VALID_START
    print(f'\n  训练集天数: {train_mask.sum()}, 验证集天数: {valid_mask.sum()}')

    # ---- 准备数据 ----
    # 申购
    X_train_p = df_clean.loc[train_mask, purchase_cols].fillna(0)
    y_train_p = df_clean.loc[train_mask, '总申购金额']
    X_valid_p = df_clean.loc[valid_mask, purchase_cols].fillna(0)
    y_valid_p = df_clean.loc[valid_mask, '总申购金额']
    # 赎回
    X_train_r = df_clean.loc[train_mask, redeem_cols].fillna(0)
    y_train_r = df_clean.loc[train_mask, '总赎回金额']
    X_valid_r = df_clean.loc[valid_mask, redeem_cols].fillna(0)
    y_valid_r = df_clean.loc[valid_mask, '总赎回金额']

    # ---- 训练申购模型 ----
    print('\n' + '=' * 60)
    print('  训练申购模型')
    print('=' * 60)
    t0 = time.time()
    lgb_p = train_lgb(X_train_p, y_train_p, X_valid_p, y_valid_p, '申购')
    xgb_p = train_xgb(X_train_p, y_train_p, X_valid_p, y_valid_p, '申购')
    ridge_p, scaler_p = train_ridge(X_train_p, y_train_p, '申购')
    print(f'  申购模型训练耗时: {time.time() - t0:.1f}s')

    # ---- 训练赎回模型 ----
    print('\n' + '=' * 60)
    print('  训练赎回模型')
    print('=' * 60)
    t0 = time.time()
    lgb_r = train_lgb(X_train_r, y_train_r, X_valid_r, y_valid_r, '赎回')
    xgb_r = train_xgb(X_train_r, y_train_r, X_valid_r, y_valid_r, '赎回')
    ridge_r, scaler_r = train_ridge(X_train_r, y_train_r, '赎回')
    print(f'  赎回模型训练耗时: {time.time() - t0:.1f}s')

    # ---- 验证集预测 & 融合权重搜索 ----
    print('\n' + '=' * 60)
    print('  验证集评估 — 网格搜索最优融合权重')
    print('=' * 60)

    preds_p = {
        'lgb': lgb_p.predict(X_valid_p),
        'xgb': xgb_p.predict(xgb.DMatrix(X_valid_p)),
        'ridge': ridge_p.predict(scaler_p.transform(X_valid_p.fillna(0))),
    }
    preds_r = {
        'lgb': lgb_r.predict(X_valid_r),
        'xgb': xgb_r.predict(xgb.DMatrix(X_valid_r)),
        'ridge': ridge_r.predict(scaler_r.transform(X_valid_r.fillna(0))),
    }

    best_w = grid_search_weights(y_valid_p, y_valid_r, preds_p, preds_r)

    # 各模型单独得分
    print('\n  --- 各模型单独得分 ---')
    for name in ['lgb', 'xgb', 'ridge']:
        total, sp, sr = full_score(
            y_valid_p.values, preds_p[name],
            y_valid_r.values, preds_r[name],
        )
        print(f'  {name:>6s}: 总分={total:.2f}  申购={sp:.2f}  赎回={sr:.2f}')

    # ---- 全量重训练 ----
    print('\n' + '=' * 60)
    print('  全量重训练（训练集 + 验证集）')
    print('=' * 60)

    X_all_p = df_clean[purchase_cols].fillna(0)
    y_all_p = df_clean['总申购金额']
    X_all_r = df_clean[redeem_cols].fillna(0)
    y_all_r = df_clean['总赎回金额']

    # LightGBM final
    dtrain_all_p = lgb.Dataset(X_all_p, y_all_p)
    lgb_final_p = lgb.train(
        {'objective': 'regression', 'metric': 'mape', 'learning_rate': 0.05,
         'num_leaves': 31, 'max_depth': 6, 'verbose': -1, 'seed': 42},
        dtrain_all_p, num_boost_round=lgb_p.best_iteration,
    )
    dtrain_all_r = lgb.Dataset(X_all_r, y_all_r)
    lgb_final_r = lgb.train(
        {'objective': 'regression', 'metric': 'mape', 'learning_rate': 0.05,
         'num_leaves': 31, 'max_depth': 6, 'verbose': -1, 'seed': 42},
        dtrain_all_r, num_boost_round=lgb_r.best_iteration,
    )

    # XGBoost final
    dtrain_all_xp = xgb.DMatrix(X_all_p, y_all_p)
    xgb_final_p = xgb.train(
        {'objective': 'reg:squarederror', 'learning_rate': 0.05,
         'max_depth': 6, 'seed': 42, 'verbosity': 0},
        dtrain_all_xp, num_boost_round=xgb_p.best_iteration,
    )
    dtrain_all_xr = xgb.DMatrix(X_all_r, y_all_r)
    xgb_final_r = xgb.train(
        {'objective': 'reg:squarederror', 'learning_rate': 0.05,
         'max_depth': 6, 'seed': 42, 'verbosity': 0},
        dtrain_all_xr, num_boost_round=xgb_r.best_iteration,
    )

    # Ridge final
    ridge_final_p, scaler_final_p = train_ridge(X_all_p, y_all_p, '申购_全量')
    ridge_final_r, scaler_final_r = train_ridge(X_all_r, y_all_r, '赎回_全量')

    # ---- 递归预测 ----
    final_models_p = {
        'lgb': lgb_final_p,
        'xgb': xgb_final_p,
        'ridge': ridge_final_p,
        'scaler': scaler_final_p,
    }
    final_models_r = {
        'lgb': lgb_final_r,
        'xgb': xgb_final_r,
        'ridge': ridge_final_r,
        'scaler': scaler_final_r,
    }

    submit = recursive_predict(
        df_clean, purchase_cols, redeem_cols,
        best_w, final_models_p, final_models_r,
    )

    # ---- 输出 ----
    print('\n' + '=' * 60)
    print('  输出提交文件')
    print('=' * 60)
    submit.to_csv(OUTPUT_FILE, index=False, header=True, encoding='utf-8-sig')
    print(f'  文件已保存: {OUTPUT_FILE}')
    print(f'\n  前5行预览:')
    print(submit.head().to_string(index=False))

    # 与8月对比
    aug_mean = df_clean[df_clean['报告日期'] >= '2014-08-01'][
        ['总申购金额', '总赎回金额']
    ].mean()
    sep_mean = submit[['申购', '赎回']].mean()
    print(f'\n  8月均值: 申购={aug_mean["总申购金额"]:,.0f}, '
          f'赎回={aug_mean["总赎回金额"]:,.0f}')
    print(f'  9月预测均值: 申购={sep_mean["申购"]:,.0f}, '
          f'赎回={sep_mean["赎回"]:,.0f}')

    print('\n' + '=' * 60)
    print('  Step 4 完成！全流程结束。')
    print('=' * 60)


if __name__ == '__main__':
    main()
