import os
import torch
import random
import numpy as np
import matplotlib.pyplot as plt
import torchvision.transforms as T
from PIL import Image
from tqdm.notebook import tqdm


def set_all_seeds(seed=42):
    # Устанавливаем seed для встроенного генератора Python
    random.seed(seed)
    # Устанавливаем seed для хэш-функции Python (опция для контроля поведения хэшей)
    os.environ['PYTHONHASHSEED'] = str(seed)
    # Устанавливаем seed для NumPy
    np.random.seed(seed)

    # Устанавливаем seed для PyTorch
    torch.manual_seed(seed)
    # Устанавливаем seed для генератора на CUDA
    torch.cuda.manual_seed(seed)
    # Отключаем недетерминированное поведение в алгоритмах CUDNN
    torch.backends.cudnn.deterministic = True
    torch.backends.cudnn.benchmark = False


def denormalize(image_tensor, mean, std):
    # Преобразуем mean и std в тензоры и переносим их на то же устройство, что и image
    tensor_mean = torch.tensor(mean).view(-1, 1, 1).to(image_tensor.device)
    tensor_std = torch.tensor(std).view(-1, 1, 1).to(image_tensor.device)

    # Денормализация: (тензор * std) + mean
    denormalize_image = image_tensor * tensor_std + tensor_mean

    # Преобразуем в диапазон [0, 255] и к типу uint8
    return (denormalize_image * 255).clamp(0, 255).byte()


def show_images(dataset, amount=3, figsize=(4, 4), classes=None, n_classes=5):
    # Получаем метки из dataset
    labels = np.array(dataset.labels)

    # Находим уникальные классы
    unique_classes = sorted(set(labels))[:n_classes]
    rows, cols = amount, len(unique_classes)

    # Изменяем figsize
    figsize = (figsize[0] * cols, figsize[1] * rows)

    fig, axes = plt.subplots(rows, cols, figsize=figsize)

    if rows == 1:
        axes = np.expand_dims(axes, axis=0)
    if cols == 1:
        axes = np.expand_dims(axes, axis=1)

    shown_indices = dict.fromkeys(unique_classes, 0)  # Отслеживаем, сколько картинок каждого класса показано

    for row in range(rows):
        for col, class_id in enumerate(unique_classes):
            # Найдем индексы всех изображений текущего класса
            class_indices = np.where(labels == class_id)[0]

            # Проверяем, сколько уже показано, и берем следующий индекс
            idx = class_indices[shown_indices[class_id] % len(class_indices)]  # Циклично берем следующий индекс
            shown_indices[class_id] += 1  # Увеличиваем счетчик для текущего класса

            # Загружаем изображение
            image = dataset.get_item(idx)['image'].resize((512, 512))

            # Определяем название класса
            class_name = f"Class: {class_id}" if classes is None else f"Class: {classes[class_id]}"

            # Отображение изображения
            ax = axes[row][col]
            ax.imshow(np.array(image))

            ax.set_title(class_name, fontsize=10)  # Белый текст для контраста
            ax.axis("off")

    # Отключаем лишние оси, если изображений меньше, чем ячеек
    for i in range(rows * cols, len(axes.flatten())):
        axes.flatten()[i].axis("off")

    plt.tight_layout()
    plt.show()


def show_texts(dataset, amount=3, classes=None):
    for i in range(amount):
        item = dataset.get_item(i)
        text = item['text']
        label = item.get('label')
        if classes is not None and label is not None:
            label = classes[label]
        print(f"{i+1}) {text[:80]}{'...' if len(text) > 80 else ''} - {label}")


# Datasets

class TextClassificationDataset(torch.utils.data.Dataset):
    tokenizer = None
    max_length = 128

    def __init__(self, texts, labels=None):
        self.texts = texts
        self.labels = labels

    def __len__(self):
        return len(self.texts)

    def __getitem__(self, idx):
        text = self.texts[idx]
        encoding = self.tokenizer(text, padding='max_length', truncation=True, max_length=self.max_length, return_tensors="pt")
        encoding = {k: v.squeeze(0) for k, v in encoding.items()}
        result = {'model_kwargs': encoding}

        # Добавляем label, если есть
        if self.labels is not None:
            result['labels'] = torch.tensor(self.labels[idx], dtype=torch.long)

        return result

    def get_item(self, idx):
        result = {'text': self.texts[idx]}
        if self.labels is not None:
            result['label'] = self.labels[idx]
        return result  # text, (label)


class ImageClassificationDataset(torch.utils.data.Dataset):
    transform = T.Compose([
        T.Resize((224, 224)),
        T.ToTensor(),
        T.Normalize(mean=0.5, std=0.5),
    ])

    def __init__(self, image_paths, labels=None, augment=False):
        self.image_paths = image_paths
        self.labels = labels
        self.augment = augment

    def __len__(self):
        return len(self.image_paths)

    def __getitem__(self, idx):
        # Считываем изображение
        image_path = self.image_paths[idx]
        image_pil = Image.open(image_path).convert("RGB")

        # Приминяем аугментации, если необходимо
        if self.augment and hasattr(self, 'augmentation'):
            image_pil = self.augmentation(image_pil)

        # Трансформируем изображение в tensor
        image_tensor = self.transform(image_pil)
        result = {'model_args': [image_tensor]} # args/kwargs для подачи в модель

        # Добавляем label, если есть
        if self.labels is not None:
            label = self.labels[idx]
            label_tensor = torch.tensor(label, dtype=torch.long)
            result['labels'] = label_tensor

        return result
    
    def get_item(self, idx):
        image_path = self.image_paths[idx]
        image_pil = Image.open(image_path)

        result = {'image': image_pil}
        if self.labels is not None:
            result['label'] = self.labels[idx]

        return result # image, (label)
    
    @classmethod
    def change_image_size(cls, new_size):
        cls.transform.transforms[0] = T.Resize(new_size)