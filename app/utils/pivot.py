
import pandas as pd
from pandas.tseries.offsets import DateOffset
import locale
locale.setlocale(locale.LC_TIME, 'fr_FR.UTF-8')

def generate_pivot_summary(df_resampled, view):
    if len(df_resampled) < 2:
        return pd.DataFrame(), []

    current_idx = df_resampled.index[-1]
    previous_idx = df_resampled.index[-2]
    last_year_idx = current_idx - DateOffset(years=1)

    try:
        last_year_value = df_resampled.loc[last_year_idx]
    except KeyError:
        pos = df_resampled.index.get_indexer([last_year_idx], method='nearest')[0]
        last_year_value = df_resampled.iloc[pos]

    
    fmt = {
        'daily': "%d/%m/%Y",
        'weekly': "Semaine du %d/%m/%Y",
        'monthly': "%B %Y",
        'yearly': "%Y"
    }.get(view, "%Y-%m-%d")

    label_current = current_idx.strftime(fmt)
    label_previous = previous_idx.strftime(fmt)
    label_last_year = last_year_idx.strftime(fmt)
    # proper encoding
    label_current = label_current.encode('latin1').decode('utf-8')
    label_previous = label_previous.encode('latin1').decode('utf-8')
    label_last_year = label_last_year.encode('latin1').decode('utf-8')

    window = {'daily': 365, 'weekly': 52, 'monthly': 12, 'yearly': 1}.get(view, 52)
    moving_avg = df_resampled.rolling(window=window, min_periods=1).mean().iloc[-1]

    current = df_resampled.loc[current_idx]
    previous = df_resampled.loc[previous_idx]

    rows, kpis = [], []
    for col in df_resampled.columns:
        val_current = current[col]
        val_previous = previous[col]
        val_diff = val_current - val_previous
        val_diff_pct = (val_diff / val_previous * 100) if val_previous != 0 else None

        val_diff_vs_avg = val_current - moving_avg[col]
        val_diff_vs_avg_pct = (val_diff_vs_avg / moving_avg[col] * 100) if moving_avg[col] != 0 else None

        val_last_year = last_year_value[col]
        val_diff_vs_last_year = val_current - val_last_year
        val_diff_vs_last_year_pct = (val_diff_vs_last_year / val_last_year * 100) if val_last_year != 0 else None

        row = {
            'Catégorie': col.replace('_', ' ').capitalize(),
            f'{label_current}': f"{val_current:.2f}",
            f'{label_previous}': f"{val_previous:.2f}",
            f'{label_current} ./. {label_previous}': f"{val_diff:+.2f} ({val_diff_pct:+.1f}%)" if val_diff_pct is not None else f"{val_diff:+.2f}",
            f'{label_last_year}': f"{val_last_year:.2f}",
            f'{label_current} ./. {label_last_year}': f"{val_diff_vs_last_year:+.2f} ({val_diff_vs_last_year_pct:+.1f}%)" if val_diff_vs_last_year_pct is not None else f"{val_diff_vs_last_year:+.2f}",
            'Moyenne mobile annuelle': f"{moving_avg[col]:.2f}",
            f'{label_current} ./. Moyenne': f"{val_diff_vs_avg:+.2f} ({val_diff_vs_avg_pct:+.1f}%)" if val_diff_vs_avg_pct is not None else f"{val_diff_vs_avg:+.2f}",
        }
        rows.append(row)
        kpis.append({
            'typeNRJ': col.replace('_', ' ').capitalize(),
            'current': val_current,
            'avg': moving_avg[col],
            'delta_vs_avg': val_diff_vs_avg,
            'delta_vs_avg_pct': val_diff_vs_avg_pct,
        })

    return pd.DataFrame(rows), kpis
