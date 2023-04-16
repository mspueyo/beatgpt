import logging
import os
import pickle

import numpy as np
import tensorflow as tf
from keras import Model
from keras import backend as K
from keras.layers import Input, Conv2D, Conv2DTranspose, ReLU, BatchNormalization, Flatten, Dense, Reshape, Activation, Lambda
from keras.optimizers import Adam
from keras.losses import MeanSquaredError

from config import AE_LOSS_WEIGHT


tf.compat.v1.disable_eager_execution()


class VariationalAutoencoder:
    """
    Variational Autoencoder (VAE) architecture.
    """

    def __init__(self, input_shape, filters, kernels, strides, latent_space_shape) -> None:
        logging.info("Start building Variational Autoencoder (VAE)...")
        
        self.input_shape = input_shape
        self.filters = filters
        self.kernels = kernels
        self.strides = strides
        self.latent_space_shape = latent_space_shape
        self.n_conv_layers = len(filters)
        assert len(self.kernels) == self.n_conv_layers, "Number of kernels should be same than number of filters."
        assert len(self.strides) == self.n_conv_layers, "Number of strides should be same than number of filters."

        self.encoder = None
        self.decoder = None
        self.model = None
        self.input = None

        self.build_model()
        logging.info("End building Variational Autoencoder model.")


    def build_model(self):
        self.build_encoder()
        self.build_decoder()
        self.build_vae()
    

    def build_encoder(self):
        # Input layer
        self.input = Input(shape=self.input_shape, name="encoder_input")
        x = self.input

        # Convolutional layers
        for l in range(self.n_conv_layers):
            conv_layer = Conv2D(
                filters = self.filters[l],
                kernel_size = self.kernels[l],
                strides = self.strides[l],
                padding = 'same',
                name = f'encoder_conv_layer_{l+1}')
            x = conv_layer(x)
            x = ReLU(name=f"encoder_relu_{l+1}")(x)
            x = BatchNormalization(name=f"encoder_bn_{l+1}")(x)
        
        # Add latent space
        self.shape_before_ls = K.int_shape(x)[1:]
        x = Flatten()(x)
        self.mu = Dense(self.latent_space_shape, name="mu")(x)
        self.sigma = Dense(self.latent_space_shape, name="sigma")(x)
        

        def normal_distribution(args):
            mu, sigma = args
            eps = K.random_normal(shape=K.shape(self.mu), mean=0., stddev=1.)
            z = mu + K.exp(sigma / 2) * eps
            return z
        x = Lambda(normal_distribution, name="encoder_output")([self.mu, self.sigma])

        self.encoder = Model(self.input, x, name="encoder")
        logging.info("Encoder built.")
        self.encoder.summary(print_fn=logging.debug)


    def build_decoder(self):
        # Input Layer
        input_layer = Input(shape=self.latent_space_shape, name="decoder_input")
        x = Dense(np.prod(self.shape_before_ls), name="decoder_dense")(input_layer)
        x = Reshape(self.shape_before_ls)(x)

        # Convolutional Layers
        for l in reversed(range(1, self.n_conv_layers)):
            conv_trans_layer = conv_trans_layer = Conv2DTranspose(
                filters = self.filters[l],
                kernel_size= self.kernels[l],
                strides = self.strides[l],
                padding = "same",
                name = f"decoder_conv_transpose_layer_{self.n_conv_layers-l}")
            x = conv_trans_layer(x)
            x = ReLU(name=f"decoder_relu_{self.n_conv_layers-l}")(x)
            x = BatchNormalization(name=f"decoder_bn_{self.n_conv_layers-l}")(x)

        # Output
        conv_trans_layer = Conv2DTranspose(
            filters = 1,
            kernel_size= self.kernels[0],
            strides = self.strides[0],
            padding = "same",
            name = f"decoder_conv_transpose_layer_{self.n_conv_layers}")
        x = conv_trans_layer(x)
        x = Activation('sigmoid', name="sigmoid_layer")(x)

        self.decoder = Model(input_layer, x, name="decoder")
        
        logging.info("Decoder built.")
        self.decoder.summary(print_fn=logging.debug)


    def build_vae(self):
        model_output = self.decoder(self.encoder(self.input))
        self.model = Model(self.input, model_output)

        logging.info("Model built.")
        self.model.summary(print_fn=logging.debug)

    
    def compile(self, learning_rate=0.0001):
        optimizer = Adam(learning_rate=learning_rate)
        self.model.compile(optimizer=optimizer, loss=self.compute_combined_loss, metrics=[self.compute_combined_loss, self.compute_kl_loss])


    def train(self, x_train, y_train, batch_size, num_epochs):
        self.model.fit(x_train, y_train,
                       batch_size=batch_size,
                       epochs=num_epochs,
                       shuffle=True)


    def compute_combined_loss(self, y_target, y_predicted):
        loss = self.compute_loss(y_target, y_predicted)
        kl_loss = self.compute_kl_loss(y_target, y_predicted)

        loss_combined = AE_LOSS_WEIGHT*loss + kl_loss
        return loss_combined
        
    
    def compute_loss(self, y_target, y_predicted):
        error = y_target - y_predicted
        loss = K.mean(K.square(error), axis=[1, 2, 3])
        return loss
    

    def compute_kl_loss(self, y_target, y_predicted):
        kl_loss = -0.5 * K.sum(1 + self.sigma - K.square(self.mu) - K.exp(self.sigma), axis=1)
        return kl_loss


    def save(self, folder="."):
        if not os.path.exists(folder):
            logging.info(f"Creating save folder {folder}.")
            os.makedirs(folder)

        # Save parameters
        logging.info("Saving model parameters.")
        params = [
            self.input_shape,
            self.filters,
            self.kernels,
            self.strides,
            self.latent_space_shape]
        path = os.path.join(folder, "params.pkl")
        with open(path, 'wb') as f:
            pickle.dump(params, f)

        # Save weights
        logging.info("Saving model weights.")
        path = os.path.join(folder, "weights.h5")
        self.model.save_weights(path)

    
    @classmethod
    def load(cls, folder="."):
        logging.info(f"Loading model from {folder}.")
        # Load parameters
        path = os.path.join(folder, "params.pkl")
        with open(path, "rb") as f:
            params = pickle.load(f)
        vae = VariationalAutoencoder(*params)

        # Load weights
        path = os.path.join(folder, "weights.h5")
        vae.model.load_weights(path)

        logging.info("Model loaded.")
        vae.model.summary(print_fn=logging.debug)
        return vae