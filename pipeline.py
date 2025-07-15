import pubchempy as pcp
import requests
from prefect import flow, task
from rdkit.Chem import Descriptors
from cleaning import null, Quantile, disp
from chembl_webresource_client.new_client import new_client
import random
from rdkit import Chem
from rdkit.Chem import QED
import matplotlib.pyplot as plt
import seaborn as sns
import pandas as pd
import numpy as np
import sqlite3
from os import path
from sklearn.ensemble import RandomForestRegressor
from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_squared_error, r2_score
import os
import pickle

#Добавляем дескрипторы из PCP, которых нет в RDkit, они константы
properties = ['XLogP',                # Коэффициент распределения октанол-вода (логарифмическое значение)
    'ExactMass',            # Точная масса
    'MonoisotopicMass',     # Моноизотопная масса
    'TPSA',                 # Полярная площадь поверхности
    'Complexity',           # Сложность структуры
    'Charge',               # Заряд молекулы
    'HBondDonorCount',      # Количество доноров водородных связей
    'HBondAcceptorCount',   # Количество акцепторов водородных связей
    'RotatableBondCount',   # Количество вращаемых связей
    'HeavyAtomCount',       # Количество тяжелых атомо
    'IsotopeAtomCount',     # Количество атомов изотопов
    'AtomStereoCount',      # Общее количество стереоатомов
    'DefinedAtomStereoCount',   # Определенное количество стереоатомов
    'UndefinedAtomStereoCount', # Неопределенное количество стереоатомов
    'BondStereoCount',          # Общее количество стереосвязей
    'DefinedBondStereoCount',   # Определенное количество стереосвязей
    'UndefinedBondStereoCount', # Неопределенное количество стереосвязей
    'CovalentUnitCount'        # Количество ковалентных единиц
]





#немного работаем с БД
@task
def coll_string(df):
    conn = sqlite3.connect(path.join("data", "Chem.db"))
    # получение уже нового ДФ
    df = pd.read_sql("SELECT * FROM first", conn)
    conn.close()


    # Только важные типы активности (ингибирование)
    valid_types = ["IC50", "Ki", "Kd"]
    df = df[df["Standard Type"].isin(valid_types)]
    df = df[df["Standard Relation"] == "="]
    df = df[df["Standard Value"].notna()]
    df = df[df["Standard Value"] > 0]
    df = df[df["Standard Value"] < 10000]
    df = df[df['Smiles'].notna()]
    df = df[df['Standard Units'].isin(['nM'])]

    # Удаляем дубликаты по структуре (SMILES)
    df = df.drop_duplicates(subset="Smiles")

    columns_to_keep = [
        "Molecule Name",
        "Smiles",
        "Standard Type",
        "Standard Value",
        "Standard Units",
        "pChEMBL Value",
        "Target Name",
        "Comment",
        "Action Type",
        "Assay Description",
        "Document Year"
    ]

    df = df[columns_to_keep]

    df.to_csv("filtered_gsk3b_deactivators.csv", index=False)
    print(f"Сохранено {len(df)} активных ингибиторов GSK-3β в 'filtered_gsk3b_deactivators.csv'")
    return df




#Добавляем дескрипторы
@task
def desc(df_1):
    for col in df_1.iloc[:, 0:2]:
        df_1[col] = df_1[col].astype(str)

    i = 0  # для подсчета, сколько дескрипторво было добавлено

    # Дескрипторы из библиотеки RDkit
    for descriptor in Descriptors.descList:
        df_1[descriptor[0]] = df_1["Smiles"].apply(lambda x: descriptor[1](Chem.MolFromSmiles(x)))  # Запись всех
        # дескрипторов из РДкита
        print(descriptor[0])  # Чтоб быть увереным в процессе
        i += 1
    i = i + len(properties)
    df_1.to_csv(path.join("/Users/kuki/PycharmProjects/DataCon/dist/", "РезультатRDKit.csv"), index=False)

    # Дескрипторы из библиотеки PCP
    pp = pd.DataFrame()  # Пустой ДФ для записи туда дескрипторов
    for i, smile in enumerate(df_1['Smiles']):
        try:
            if pd.isna(smile):
                continue
            find = pcp.get_properties(properties, smile, namespace='smiles', as_dataframe=True)
            if not find.empty:
                pp = pd.concat([pp, find.iloc[[0]]], ignore_index=True)
            else:
                pp = pd.concat([pp, pd.DataFrame([{}])], ignore_index=True)
        except Exception as e:
            print(f"⚠️ Ошибка на строке {i}: {e}")
            pp = pd.concat([pp, pd.DataFrame([{}])], ignore_index=True)

        print(len(pp), i)  # Чтобы быть уверенным в процессе
        if len(pp) % 100 == 0:
            pp.to_csv(path.join("/Users/kuki/PycharmProjects/DataCon/dist/", "Результатbroke.csv"),
                      index=False)  # на всякий случай сохраняем каждые 100стр, если программа зависнет или пропадет связь с сервером.
    pd.concat([df_1, pp], axis=1).to_csv(path.join("/Users/kuki/PycharmProjects/DataCon/dist/", "Результат.csv"),
                                         index=False)
    print(f'Добавлено {i} дескрипторов в датасет.')
    return df_1





#Провоеряем, чтоб все полученные значения, были в float
@task
def coll_float(df):
    # Определим строковые и нестроковые столбцы
    string_columns = df.select_dtypes(include=['object', 'string']).columns.tolist()
    other_columns = [col for col in df.columns if col not in string_columns]
    # Переставим порядок столбцов
    df = df[string_columns + other_columns]

    for col in df.iloc[:, df.select_dtypes(include=['object', 'string']).shape[1]:len(df.columns)]:
        df[col] = np.where(df[col] == 'no', 0, df[col])  # меняем no на 0 если есть
        df[col] = pd.to_numeric(df[col], errors='coerce')
    return df




#Сохраняет с полученными дескрипторами. Добавляет новое вещество в DB, когда мы его вводим через бота
@task
def save_desc(df):
    conn = sqlite3.connect(path.join("data", "Chem.db"))
    df.to_sql("Descriptors", conn, if_exists="append", index=False)
    conn.close()
    return




#Обрабатываем и очищаем ДатаСет заново после добавление нового вещества, так как это будет влиять на выбросы и прочие
# показатели
@task
def cleaning():
    conn = sqlite3.connect(path.join("data", "Chem.db"))
    #получение уже нового ДФ
    df = pd.read_sql("SELECT * FROM Descriptors", conn)
    null(df)
    disp(df)
    Quantile(df)
    # Cейв после очистки
    df.to_sql("Results", conn, if_exists="replace", index=False)
    conn.close()
    return df




#линейная регрессия
@task
def regTREE():
    # Подключение к базе
    db_path = path.join("data", "Chem.db")
    conn = sqlite3.connect(db_path)
    df = pd.read_sql("SELECT * FROM Descriptors", conn)
    conn.close()

    target_column = "Standard Value"

    X = df.drop(columns=[target_column])
    y = df[target_column]
    X = X.select_dtypes(include=[np.number])

    # Обработка бесконечностей и пропусков
    X = X.replace([np.inf, -np.inf], np.nan)
    X = X.dropna()
    y = y.loc[X.index]

    # Логарифмирование целевой переменной
    y = np.log1p(y)

    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)


    model = RandomForestRegressor(n_estimators=100, random_state=42)
    model.fit(X_train, y_train)


    y_pred = model.predict(X_test)

    # Метрики
    max_val = X.max().max()
    mse = mean_squared_error(y_test, y_pred)
    r2 = r2_score(y_test, y_pred)

    # Вывод
    print(f"Максимальное значение в X: {max_val:.2f}")
    print(f"MSE: {mse:.2f}")
    print(f"R2: {r2:.2f}")

    with open("model_activity.pkl", "wb") as f:
        pickle.dump(model, f)

    return max_val, mse, r2, model, X_test, y_test, y_pred





#делаем графики
@task
def plot_model_performance(y_true, y_pred, save_path="plots"):

    # Создаём папку для сохранения графиков, если не существует
    os.makedirs(save_path, exist_ok=True)

    residuals = y_true - y_pred

    # 1. Residuals Plot
    plt.figure(figsize=(6, 5))
    sns.scatterplot(x=y_pred, y=residuals, alpha=0.6)
    plt.axhline(0, color='red', linestyle='--')
    plt.xlabel('Предсказанные значения')
    plt.ylabel('Остатки')
    plt.title('Residuals Plot')
    plt.tight_layout()
    plt.savefig(f"{save_path}/residuals_plot.jpg", dpi=300)
    plt.show()

    # 2. Histogram of Residuals
    plt.figure(figsize=(6, 5))
    sns.histplot(residuals, bins=30, kde=True)
    plt.xlabel('Остатки')
    plt.title('Гистограмма Остатков')
    plt.tight_layout()
    plt.savefig(f"{save_path}/residuals_histogram.jpg", dpi=300)
    plt.show()

    # 3. Parity Plot
    plt.figure(figsize=(6, 5))
    sns.regplot(x=y_true, y=y_pred, scatter_kws={'alpha': 0.6}, line_kws={"color": "red"})
    plt.xlabel('Истинные значения')
    plt.ylabel('Предсказанные значения')
    plt.title('Parity Plot')
    plt.tight_layout()
    plt.savefig(f"{save_path}/parity_plot.jpg", dpi=300)
    plt.show()





@task
def theend(generated_smiles):
    def calc_features_dummy(smiles):
        return np.random.rand(213)
    class DummyModel:
        def predict(self, X):
            return np.array([random.uniform(5,8) for _ in range(X.shape[0])])

    activity_model = DummyModel()

    def predict_activity(smiles):
        feats = calc_features_dummy(smiles)
        X = feats.reshape(1, -1)
        pred = activity_model.predict(X)
        return pred[0]

    def predict_toxicity(smiles):
        return 0 if random.random() > 0.1 else 1

    def is_valid_smiles(smiles):
        mol = Chem.MolFromSmiles(smiles)
        return mol is not None

    filtered = []

    for sm in generated_smiles:
        if not is_valid_smiles(sm):
            continue

        mol = Chem.MolFromSmiles(sm)
        activity = predict_activity(sm)
        toxicity = predict_toxicity(sm)
        qed_score = QED.qed(mol)

        if activity >= 6.0 and qed_score >= 0.5 and toxicity == 0:
            filtered.append({
                'smiles': sm,
                'activity': activity,
                'qed': qed_score,
                'toxicity': toxicity
            })

    if len(filtered) == 0:
        print("Нет молекул, удовлетворяющих условиям фильтрации")
    else:
        df_filtered = pd.DataFrame(filtered, columns=['smiles', 'activity', 'qed', 'toxicity'])
        df_filtered = df_filtered.sort_values(by=['activity', 'qed'], ascending=False).reset_index(drop=True)
        print(f"Отобрано молекул: {len(df_filtered)}")
        print(df_filtered)
        df_filtered.to_csv("filtered_molecules.csv", index=False)





#парсим БД
@flow
def firsttime(chem_name):

    # 1. Поиск целевой мишени по названию
    target_name = chem_name
    targets = new_client.target.filter(target_components__component_synonyms__icontains=target_name)

    target_id = targets[0]['target_chembl_id']
    print("Target ChEMBL ID:", target_id)

    # 3. Загрузка bioactivity данных
    activities = new_client.activity

    # 4. Преобразуем в DataFrame
    data = pd.DataFrame(activities)
    # 6. Сохраняем в SCLite
    conn = sqlite3.connect(path.join("data", "Chem.db"))
    data.to_sql("first", conn, if_exists="append", index=False)

    return




#генерируем смайлсы
@task
def generate():
    # %%
    import torch
    import torch.nn as nn
    import numpy as np
    import selfies as sf
    import random

    # === Параметры ===
    SEQ_LEN = 100
    N_SAMPLES = 50
    EPOCHS = 5

    # === Загрузка данных ===
    with open("data/train.smi", "r") as f:
        smiles_list = [line.strip() for line in f if line.strip()]

    # === Конвертация SMILES → SELFIES ===
    selfies_list = [sf.encoder(s) for s in smiles_list]
    alphabet = list(set("".join(selfies_list)))
    char_to_idx = {ch: i + 1 for i, ch in enumerate(alphabet)}  # 0 — padding
    idx_to_char = {i: ch for ch, i in char_to_idx.items()}

    vocab_size = len(char_to_idx) + 1

    def selfies_to_tensor(selfies_str):
        idxs = [char_to_idx[ch] for ch in selfies_str if ch in char_to_idx]
        return torch.tensor(idxs[:SEQ_LEN] + [0] * (SEQ_LEN - len(idxs)), dtype=torch.long)

    tensor_data = torch.stack([selfies_to_tensor(s) for s in selfies_list])

    # === Модель ===
    class LSTMGen(nn.Module):
        def __init__(self, vocab_size, hidden_size=256):
            super().__init__()
            self.emb = nn.Embedding(vocab_size, 128, padding_idx=0)
            self.lstm = nn.LSTM(128, hidden_size, batch_first=True)
            self.fc = nn.Linear(hidden_size, vocab_size)

        def forward(self, x, hidden=None):
            x = self.emb(x)
            out, hidden = self.lstm(x, hidden)
            out = self.fc(out)
            return out, hidden

    model = LSTMGen(vocab_size)
    optimizer = torch.optim.Adam(model.parameters(), lr=0.003)
    criterion = nn.CrossEntropyLoss(ignore_index=0)

    # === Обучение ===
    for epoch in range(EPOCHS):
        model.train()
        total_loss = 0
        for seq in tensor_data:
            seq = seq.unsqueeze(0)
            inputs = seq[:, :-1]
            targets = seq[:, 1:]

            out, _ = model(inputs)
            loss = criterion(out.view(-1, vocab_size), targets.view(-1))

            optimizer.zero_grad()
            loss.backward()
            optimizer.step()
            total_loss += loss.item()
        print(f"Epoch {epoch + 1}/{EPOCHS}, Loss: {total_loss:.2f}")

    # === Генерация SELFIES ===
    def generate_selfie(model, max_len=SEQ_LEN):
        model.eval()
        input_seq = torch.zeros(1, 1, dtype=torch.long)
        hidden = None
        result = []

        for _ in range(max_len):
            out, hidden = model(input_seq, hidden)
            probs = torch.softmax(out[:, -1, :], dim=-1).detach().numpy().flatten()
            idx = np.random.choice(len(probs), p=probs)
            if idx == 0:
                break
            ch = idx_to_char.get(idx, "")
            result.append(ch)
            input_seq = torch.tensor([[idx]], dtype=torch.long)

        return "".join(result)

    generated_smiles = []
    for _ in range(N_SAMPLES):
        selfie = generate_selfie(model)
        try:
            smiles = sf.decoder(selfie)
            generated_smiles.append(smiles)
        except Exception:
            continue

    # === Сохраняем результат ===
    with open("generated_smiles.smi", "w") as f:
        for sm in generated_smiles:
            f.write(sm + "\n")

    print(f"Сгенерировано {len(generated_smiles)} SMILES и сохранено в generated_smiles.smi")
    return generated_smiles




@flow
def ending():
    theend(firsttime)



@flow
def collecting(df, anarchy, antichrist, degenerate):
    if anarchy == True:
        firsttime(antichrist)

    if degenerate == True:
        ending
    #Преобразуем нужные столбцы в строковый формат, на всякий случай
    string = coll_string(df)
    print(df)
    #Добавляем дескрипторы
    descriptors = desc(string)

    # Провоеряем, чтоб все полученные значения, были во float
    float = coll_float(descriptors)

    #Сохраняем в БД промежуточный результат
    save_desc(float)

    #Очистка данных
    cleaning()

    max_val, mse, r2, model, X_test, y_test, y_pred = regTREE()
    plot_model_performance(y_test, y_pred)

    return
