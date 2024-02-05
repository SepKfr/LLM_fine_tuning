import random
import numpy as np
from transformers import GPT2Tokenizer, GPT2LMHeadModel
from datasets import load_dataset
from torch.utils.data import DataLoader
import torch
import huggingface_hub

from coarse_fine_grained import GPT2Classifier2
from gptclassifier import GPT2Classifier
from torcheval.metrics.functional import multiclass_f1_score, multiclass_accuracy

torch.manual_seed(2024)
random.seed(2024)
np.random.seed(2024)

huggingface_hub.login()

# Set device for GPU usage (if available)
device = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")

train_data = load_dataset("yelp_review_full", split="train")
train_eval = train_data.train_test_split(test_size=0.1, stratify_by_column="label")
train_data = train_eval.get("train")
valid_data = train_eval.get("test")
test_data = load_dataset("yelp_review_full", split="test")

product_reviews_train = train_data.filter(lambda x: "laptop" in x["text"])
product_reviews_valid = valid_data.filter(lambda x: "laptop" in x["text"])
product_reviews_test = test_data.filter(lambda x: "laptop" in x["text"])

max_value = max(product_reviews_train, key=lambda x: x["label"])["label"]

tokenizer = GPT2Tokenizer.from_pretrained("gpt2")
tokenizer.pad_token = tokenizer.eos_token


def collate_fn(batch):
    # Extract sequences
    sequences = [item["text"] for item in batch]

    # Pad sequences using tokenizer directly
    encoded_data = tokenizer(
      sequences, padding=True, truncation=True, max_length=512
    )

    # Access padded input_ids and labels
    padded_sequences = encoded_data["input_ids"]

    padded_sequences = torch.tensor(padded_sequences, device=device)

    # Filter out None values from labels:

    labels = [item.get("label") for item in batch]
    labels = torch.tensor(labels, device=device)

    return padded_sequences, labels


loss_fn = torch.nn.CrossEntropyLoss()

train_dataloader = DataLoader(product_reviews_train, batch_size=16, collate_fn=collate_fn)
valid_dataloader = DataLoader(product_reviews_valid, batch_size=16, collate_fn=collate_fn)
test_dataloader = DataLoader(product_reviews_test, batch_size=16, collate_fn=collate_fn)


def run(model, optim):
    epochs = 15
    for epoch in range(epochs):
        model.train()
        for i, batch in enumerate(train_dataloader):

            input_ids, labels = batch
            outputs = model(input_ids).squeeze(1)
            loss = loss_fn(outputs, labels)
            loss.backward()
            optim.step()
            optim.zero_grad()

        print("train loss {:.3f}".format(loss.item()))

        model.eval()
        for batch in valid_dataloader:

            input_ids, labels = batch
            outputs = model(input_ids).squeeze(1)
            loss = loss_fn(outputs, labels)

        print("valid loss {:.3f}".format(loss.item()))

    model.eval()

    tot_outputs = torch.zeros(len(test_dataloader), 16, max_value+1)
    tot_labels = torch.zeros(len(test_dataloader), 16)

    for i, batch in enumerate(test_dataloader):
        input_ids, labels = batch
        outputs = model(input_ids).squeeze(1).detach().cpu()
        tot_outputs[i, :outputs.shape[0], :] = outputs
        tot_labels[i, :labels.shape[0]] = labels

    tot_outputs = tot_outputs.reshape(-1, max_value+1)
    tot_labels = tot_labels.reshape(-1)
    f_1 = multiclass_f1_score(tot_outputs, tot_labels)
    acc = multiclass_accuracy(tot_outputs, tot_labels)

    return f_1, acc


gpt_model = GPT2LMHeadModel.from_pretrained("gpt2")

gptclassifier = GPT2Classifier(gpt_model, max_value+1).to(device)
optimizer = torch.optim.AdamW(gptclassifier.parameters())

f_1, acc = run(gptclassifier, optimizer)

# gptclassifier2 = GPT2Classifier2(d_model=64, gpt_model=gpt_model, num_classes=max_value+1)
# optimizer = torch.optim.AdamW(gptclassifier2.parameters(), lr=1e-5)
#
# test_loss2 = run(gptclassifier2, optimizer)

print("f_1 of GPT: {:.3f}".format(f_1))
print("acc of GPT: {:.3f}".format(acc))
#print("loss of GPT BlurDenoise: {:.3f}".format(test_loss2))

# prompt = "Write a creative description for a product:"
# new_description = model.generate(
#     tokenizer.encode(prompt, return_tensors="pt").to(device),
#     max_length=100, num_beams=2, early_stopping=True
# )
# decoded_description = tokenizer.decode(new_description[0], skip_special_tokens=True)
# print(decoded_description)
