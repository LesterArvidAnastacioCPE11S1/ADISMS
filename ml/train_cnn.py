"""Train Alternative C: MobileNetV3 (or ResNet18) with transfer learning.

Dataset layout (one folder per Product ID):

    data/products/P001/*.jpg
    data/products/P002/*.jpg

    python ml/train_cnn.py --data data/products --out data/models --epochs 12

The trained weights and class order are saved to data/models/cnn.pt.
The web app loads that file automatically; without it the CNN engine reports
itself as unavailable and "auto" falls back to template matching.
"""
import argparse
import json
import random
from datetime import datetime
from pathlib import Path

MEAN = (0.485, 0.456, 0.406)
STD = (0.229, 0.224, 0.225)


def parse_args():
    parser = argparse.ArgumentParser(description="Train the ADISMS CNN.")
    parser.add_argument("--data", default="data/products", help="root folder of labeled product photos")
    parser.add_argument("--out", default="data/models", help="folder for cnn.pt and class_map.json")
    parser.add_argument("--arch", default="mobilenet_v3_small",
                        choices=["mobilenet_v3_small", "mobilenet_v3_large", "resnet18"])
    parser.add_argument("--epochs", type=int, default=12)
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--lr", type=float, default=1e-3)
    parser.add_argument("--val-split", type=float, default=0.2)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--workers", type=int, default=0)
    return parser.parse_args()


def build_model(arch, num_classes):
    from torch import nn
    from torchvision import models

    if arch == "resnet18":
        model = models.resnet18(weights=models.ResNet18_Weights.DEFAULT)
        model.fc = nn.Linear(model.fc.in_features, num_classes)
        features = [p for name, p in model.named_parameters() if not name.startswith("fc")]
        head = list(model.fc.parameters())
    else:
        weights = (models.MobileNet_V3_Small_Weights.DEFAULT if arch == "mobilenet_v3_small"
                   else models.MobileNet_V3_Large_Weights.DEFAULT)
        model = getattr(models, arch)(weights=weights)
        model.classifier[3] = nn.Linear(model.classifier[3].in_features, num_classes)
        features = list(model.features.parameters())
        head = list(model.classifier.parameters())
    return model, features, head


def transforms():
    from torchvision import transforms as T
    train = T.Compose([
        T.RandomResizedCrop(224, scale=(0.7, 1.0)),
        T.RandomHorizontalFlip(),
        T.ColorJitter(brightness=0.2, contrast=0.2, saturation=0.2),
        T.ToTensor(),
        T.Normalize(MEAN, STD),
    ])
    val = T.Compose([T.Resize(256), T.CenterCrop(224), T.ToTensor(), T.Normalize(MEAN, STD)])
    return train, val


def accuracy(model, loader, device):
    import torch
    model.eval()
    correct = total = 0
    with torch.no_grad():
        for images, labels in loader:
            images, labels = images.to(device), labels.to(device)
            predictions = model(images).argmax(dim=1)
            correct += int((predictions == labels).sum())
            total += labels.numel()
    return correct / total if total else 0.0


def main():
    args = parse_args()

    import torch
    from torch import nn
    from torch.utils.data import DataLoader, Subset
    from torchvision import datasets

    random.seed(args.seed)
    torch.manual_seed(args.seed)

    data_root = Path(args.data)
    if not data_root.is_dir():
        raise SystemExit(f"Dataset folder not found: {data_root}")

    base = datasets.ImageFolder(str(data_root))
    classes = base.classes
    if len(classes) < 2:
        raise SystemExit("Collect photos for at least 2 products under data/products/<product_id>/.")
    if len(base) < len(classes) * 2:
        print(f"Warning: only {len(base)} images for {len(classes)} classes. "
              "Collect at least 5-10 photos per product for reliable accuracy.")

    indices = list(range(len(base)))
    random.shuffle(indices)
    val_size = max(1, int(len(indices) * args.val_split)) if len(indices) > 2 else 0
    train_indices = indices[val_size:]
    val_indices = indices[:val_size]

    train_tf, val_tf = transforms()
    train_dataset = Subset(datasets.ImageFolder(str(data_root), transform=train_tf), train_indices)
    val_dataset = Subset(datasets.ImageFolder(str(data_root), transform=val_tf), val_indices) if val_indices else None

    train_loader = DataLoader(train_dataset, batch_size=args.batch_size, shuffle=True,
                              num_workers=args.workers)
    val_loader = (DataLoader(val_dataset, batch_size=args.batch_size, num_workers=args.workers)
                  if val_dataset else None)

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model, feature_params, head_params = build_model(args.arch, len(classes))
    model.to(device)

    for param in feature_params:
        param.requires_grad = False
    optimizer = torch.optim.AdamW(head_params, lr=args.lr, weight_decay=1e-4)
    criterion = nn.CrossEntropyLoss()
    unfreeze_at = max(1, args.epochs // 2)

    best_state = None
    best_val = -1.0
    print(f"Training {args.arch} on {len(classes)} classes "
          f"({len(train_indices)} train / {len(val_indices)} val images) on {device}")

    for epoch in range(1, args.epochs + 1):
        if epoch == unfreeze_at:
            for param in feature_params:
                param.requires_grad = True
            optimizer = torch.optim.AdamW(model.parameters(), lr=args.lr / 10, weight_decay=1e-4)
            print("Fine-tuning the full network from epoch", epoch)

        model.train()
        running_loss = seen = correct = 0
        for images, labels in train_loader:
            images, labels = images.to(device), labels.to(device)
            optimizer.zero_grad()
            outputs = model(images)
            loss = criterion(outputs, labels)
            loss.backward()
            optimizer.step()
            running_loss += float(loss) * labels.numel()
            seen += labels.numel()
            correct += int((outputs.argmax(dim=1) == labels).sum())

        train_loss = running_loss / max(1, seen)
        train_acc = correct / max(1, seen)
        val_acc = accuracy(model, val_loader, device) if val_loader else float("nan")
        report = f"epoch {epoch:02d}/{args.epochs}  loss {train_loss:.3f}  train_acc {train_acc:.3f}"
        if val_loader:
            report += f"  val_acc {val_acc:.3f}"
        print(report)

        score = val_acc if val_loader else train_acc
        if score >= best_val:
            best_val = score
            best_state = {key: value.detach().cpu().clone() for key, value in model.state_dict().items()}

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    checkpoint = {
        "arch": args.arch,
        "classes": classes,
        "state_dict": best_state if best_state is not None else model.state_dict(),
        "val_accuracy": best_val,
        "trained_at": datetime.now().isoformat(timespec="seconds"),
    }
    torch.save(checkpoint, out_dir / "cnn.pt")
    (out_dir / "class_map.json").write_text(
        json.dumps({str(index): name for index, name in enumerate(classes)}, indent=2), encoding="utf-8")
    print(f"Saved {out_dir / 'cnn.pt'} (best score {best_val:.3f}) and class_map.json")
    print("Restart the web app, then run: python tools/evaluate_recognition.py --engine cnn")


if __name__ == "__main__":
    main()
