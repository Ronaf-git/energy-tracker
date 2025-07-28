# utils/plotting.py
import matplotlib.pyplot as plt
import io
import base64

def generate_plot_image(df_diff, data_type='all', view='weekly'):
    plt.figure(figsize=(10, 6))
    if data_type == 'all':
        for col in df_diff.columns:
            plt.plot(df_diff.index, df_diff[col], label=f'Δ {col}')
    else:
        plt.plot(df_diff.index, df_diff[data_type], label=f'Δ {data_type}')

    plt.xticks(rotation=45)
    plt.xlabel('Date')
    plt.ylabel('Unité d\'œuvre')
    plt.title(f'Variation ({view.capitalize()})')
    plt.legend()
    plt.tight_layout()

    img = io.BytesIO()
    plt.savefig(img, format='png')
    plt.close()
    img.seek(0)
    return base64.b64encode(img.getvalue()).decode()
