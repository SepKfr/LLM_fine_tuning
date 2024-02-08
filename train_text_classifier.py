import evaluate
import torch
from datasets import load_dataset
from torch import nn
from torch.utils.data import DataLoader
from transformers import AutoTokenizer, AutoModelForSequenceClassification, Adafactor
from transformers.optimization import AdafactorSchedule

imdb = load_dataset("imdb")
tokenizer = AutoTokenizer.from_pretrained("distilbert-base-uncased")

id2label = {0: "NEGATIVE", 1: "POSITIVE"}
label2id = {"NEGATIVE": 0, "POSITIVE": 1}

accuracy = evaluate.load("accuracy")

device = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")

model = AutoModelForSequenceClassification.from_pretrained(
    "distilbert-base-uncased", num_labels=2, id2label=id2label, label2id=label2id).to(device)

optimizer = Adafactor(model.parameters(), scale_parameter=True, relative_step=True, warmup_init=True, lr=None)
lr_scheduler = AdafactorSchedule(optimizer)


def collate_fn(batch):
    # Extract sequences
    sequences = [item["text"] for item in batch]

    # Pad sequences using tokenizer directly
    encoded_data = tokenizer(sequences, return_tensors="pt",
                             truncation=True, max_length=64, padding=True)

    # Filter out None values from labels:

    labels = [item.get("label") for item in batch]
    labels = torch.tensor(labels, device=device).to(torch.long)

    return encoded_data.to(device), labels


train_dataloader = DataLoader(imdb["train"], batch_size=64, collate_fn=collate_fn)
test_dataloader = DataLoader(imdb["test"], batch_size=64, collate_fn=collate_fn)

loss_fn = nn.CrossEntropyLoss()
epochs = 50
best_loss = 1e10
check_p_epoch = 0

for epoch in range(epochs):
    tot_loss = 0
    model.train()
    for batch in train_dataloader:

        inputs, labels = batch
        outputs = model(**inputs)
        predicted = outputs.logits
        loss = loss_fn(predicted, labels)
        tot_loss += loss.item()
        loss.backward()
        optimizer.step()
        lr_scheduler.step()
        optimizer.zero_grad()

    print("train loss: {:.3f}".format(tot_loss))
    if tot_loss < best_loss:
        best_loss = tot_loss
        check_p_epoch = epoch
    if epoch - check_p_epoch >= 3:
        break


model.eval()
tot_acc = 0
for batch in test_dataloader:
    inputs, labels = batch
    predicted = model(**inputs).logits
    predicted = torch.argmax(predicted, dim=-1)
    acc = accuracy.compute(predictions=predicted, references=labels)
    tot_acc += acc['accuracy']

print("total accuracy: {:.3f}".format(tot_acc/len(test_dataloader)))
