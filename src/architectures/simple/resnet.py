#!/usr/bin/env python
# coding: utf-8

# In[ ]:


import os

print(os.getcwd())

import keras
import pandas as pd
import numpy as np
from utils.save_model import save_model, model_set
from sklearn.metrics import classification_report
from sklearn.model_selection import train_test_split
from keras.models import Model
from keras.layers import Dense, GlobalAveragePooling2D
from keras.applications import resnet_v2
from keras_preprocessing.image import ImageDataGenerator

# os.chdir("../../../")
print(os.getcwd())


# In[ ]:


#DATASET_FOLDER = '../../../data/dataset/'
DATASET_FOLDER = 'data/dev_dataset/'
SEED = 17


# In[ ]:


data = pd.read_csv(os.path.join(DATASET_FOLDER + 'train.csv'))

# preprocess
data = data.fillna(0)

# drop lateral images
data = data[~data['Frontal/Lateral'].str.contains("Lateral")]

# drop unrelevant columns
data = data.drop(["Sex", "Age", "Frontal/Lateral", "AP/PA"], axis=1)

# deal with uncertanty (-1) values
data = data.replace(-1, 1)

np.random.seed(SEED)
data_train, data_test = train_test_split(data, test_size=0.2)
data_train, data_val = train_test_split(data_train, test_size=0.2)


# In[ ]:


print(data_train.columns)


# In[ ]:


train_datagen = ImageDataGenerator(rescale=1./255)
valid_datagen = ImageDataGenerator(rescale=1./255.)
test_datagen = ImageDataGenerator(rescale=1./255.)


# In[ ]:


target_size = (224, 224)
train_generator = train_datagen.flow_from_dataframe(
    dataframe=data_train,
    directory=DATASET_FOLDER,
    x_col='Path',
    y_col=list(data_train.columns[2:16]),
    class_mode='other',
    target_size=target_size,
    batch_size=32
)
valid_generator = valid_datagen.flow_from_dataframe(
    dataframe=data_val,
    directory=DATASET_FOLDER,
    x_col='Path',
    y_col=list(data_val.columns[2:16]),
    class_mode='other',
    target_size=target_size,
    batch_size=32
)
test_generator = test_datagen.flow_from_dataframe(
    dataframe=data_test,
    directory=DATASET_FOLDER,
    x_col="Path",
    y_col=list(data_test.columns[2:16]),
    class_mode="other",
    target_size=target_size,
    shuffle=False,
    batch_size=1
)


# In[ ]:


base_model = resnet_v2.ResNet152V2(include_top=False, weights='imagenet')

# add global pooling and dense output layer
x = base_model.output
x = GlobalAveragePooling2D()(x)
x = Dense(1024, activation='relu')(x)
prediction_layer = Dense(14, activation='sigmoid')(x)

model = Model(inputs=base_model.input, outputs=prediction_layer)


# In[ ]:


# freeze all convolutional layers
for layer in base_model.layers:
    layer.trainable = False


# In[ ]:


# compile model
adam = keras.optimizers.Adam()
model.compile(optimizer=adam, loss='binary_crossentropy', metrics=['accuracy'])


# In[ ]:


# fit model
num_epochs = 3
STEP_SIZE_TRAIN = train_generator.n // train_generator.batch_size
STEP_SIZE_VALID = valid_generator.n // valid_generator.batch_size
STEP_SIZE_TEST = test_generator.n // test_generator.batch_size


result = model.fit_generator(generator=train_generator,
                             steps_per_epoch=STEP_SIZE_TRAIN,
                             validation_data=valid_generator,
                             validation_steps=STEP_SIZE_VALID,
                             epochs=num_epochs)


# In[ ]:


model_id = save_model(model, result.history, 'resnetv2',
                      'resnetv2_151.h5')


# In[ ]:


print("predicting...")
test_generator.reset()
pred = model.predict_generator(test_generator, steps=STEP_SIZE_TEST, verbose=1)


# In[ ]:


pred_bool = (pred >= 0.5)
y_pred = np.array(pred_bool, dtype=int)

dtest = data_test.to_numpy()
y_true = np.array(dtest[:, 2:16], dtype=int)
report = classification_report(
    y_true, y_pred, target_names=list(data_test.columns[1:15]))
model_id = model_set(model_id, 'classification_report', report)


# In[ ]:


score, acc = model.evaluate_generator(
    test_generator, steps=STEP_SIZE_TEST, verbose=1)
print('Test score:', score)
print('Test accuracy:', acc)
model_id = model_set(model_id, 'test', (score, acc))


# In[ ]:


print("completed training and evaluation")
