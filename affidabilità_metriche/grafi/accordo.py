import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns

df = pd.read_csv("./evalData.csv")
metrics_cols = [
    c for c in df.columns if c not in ["Modello", "Domanda", "Risposta", "Retrieval"]
]

grouped_agreement = df.groupby("Modello")[metrics_cols].mean() * 100
df_plot = grouped_agreement.reset_index().melt(
    id_vars="Modello", var_name="Metrica", value_name="Accordo"
)

plt.figure(figsize=(14, 7))
sns.set_style("whitegrid")
ax = sns.barplot(data=df_plot, x="Metrica", y="Accordo", hue="Modello", palette="muted")
plt.title(
    " Accordo con GPT4.1 e Qwen2.5 (8 domande)",
    fontsize=16,
    pad=20,
)
plt.ylabel("Accordo percentuale", fontsize=12)
plt.xticks(rotation=45)
plt.ylim(0, 110)
plt.legend(title="Giudice", bbox_to_anchor=(1.05, 1), loc="upper left")
for p in ax.patches:
    if p.get_height() > 0:
        ax.annotate(
            f"{p.get_height():.0f}%",
            (p.get_x() + p.get_width() / 2.0, p.get_height()),
            ha="center",
            va="center",
            xytext=(0, 7),
            textcoords="offset points",
            fontsize=9,
            fontweight="bold",
        )
plt.tight_layout()
plt.savefig("barchart_eval.png")

df["Label"] = df["Domanda"].astype(str) + " - " + df["Modello"]
df = df.set_index("Label")[metrics_cols]

plt.figure(figsize=(12, 8))
sns.heatmap(df, annot=True, cmap="RdYlGn", cbar=False, linewidths=0.5)
plt.title(
    "Accordo per ogni domanda (1=Sì, 0=No)",
    fontsize=14,
    pad=15,
)
plt.ylabel("")
plt.tight_layout()
plt.savefig("heatmap_eval.png")
plt.show()
