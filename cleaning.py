import pandas as pd




# Поиск отсутствующих значений и удаление дубликатов
def null(df):
    nan = len(df) * (0.8)  # 30% пропусков довольно высоко для статистических методов, нам придется их удалить. Но для большей точности уменьшаем до 20%
    df = df.dropna(axis=1, thresh=nan)
    df.drop_duplicates()

    # если остались другие значения, где пустые поля
    numeric_columns = df.select_dtypes(include=['number']).columns
    missing_values = df[numeric_columns].isnull().sum().sort_values(ascending=False)
    # Выбираем только те столбцы, где есть пропуски
    columns_with_missing = missing_values[missing_values > 0]

    if not columns_with_missing.empty:
        print("Количество пропущенных значений в числовых столбцах:") #Оставил, чтоб если что смотреть при исполнении
        for col, count in columns_with_missing.items():
            print(f"{col}: {count} отсутствующих значений. Заполнено средним.")
            df[col].fillna(df[col].mean(), inplace=True)
    else:
        print("Пропущенные значения в числовых столбцах не найдены.")
    return df



# дисперсия
def disp(df):
    # Отделяем столбецы, которые не будем использовать для отбора
    first_column = df.iloc[:, 0: df.select_dtypes(include=['object', 'string']).shape[1]]
    df.drop(first_column, axis=1, inplace=True)

    disp = df.var()

    # Устанавливаем порог
    FILTER_THRESHOLD = 0.1
    to_drop = [column for column in disp.index if disp[column] < FILTER_THRESHOLD]
    df = df.drop(to_drop, axis=1)

    # Соединяем первые столбцы с отобранными признаками
    df = pd.concat([first_column, df], axis=1)

    return df


# ищет выбросы по всем столбцам и удаляет строки с выбросами, хотя бы по одному параметру
def Quantile(df):
    for column_name in df.columns[df.select_dtypes(include=['object', 'string']).shape[1]:len(df.columns)]:
        # Обнаруживаем выбросы
        Q1 = df[column_name].quantile(0.25)
        Q3 = df[column_name].quantile(0.75)
        IQR = Q3 - Q1
        # Удаление выбросов из основного DataFrame
        df2 = df[(df[column_name] >= Q1 - 1.5 * IQR) & (df[column_name] <= Q3 + 1.5 * IQR)]
    df = df2
    return df
