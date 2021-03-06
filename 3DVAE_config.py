#####################################################
# Introspective Variational Autoencoder Config File #
#####################################################
# A Brock, 2016
import numpy as np
import matplotlib.pyplot as plt

from keras.utils.visualize_util import plot
from keras.models import Model
from keras import backend as K
from keras import objectives
from keras.datasets import mnist

from keras.models import load_model

from keras.layers import Input, Dense, Convolution2D, MaxPooling2D, UpSampling2D,Lambda
from keras.layers.core import Dense, Dropout, Flatten, Reshape

K.set_image_dim_ordering('tf')


class VAE:

    # Start with a low learning rate then increase learning rate on second epoch
    # lr_schedule = {0: 0.0001, 1: 0.005}
    # Configuration Dictionary
    cfg = {'batch_size': 100,
           # 'learning_rate': lr_schedule,
           'reg': 0.001,
           'momentum': 0.9,
           'input_dim': (28, 28),
           'n_channels': 1,
           'n_classes': 10,
           'max_epochs': 50,
           'latent_dim': 2,
           'intermediate_dim': 32,
           }
    data = []
    enc_dec =[]
    enc =[]
    dec =[]
    rmnist = []

    if K.image_dim_ordering() == 'tf':
        original_img_size = (28, 28, 1)
    else:
        original_img_size = (1, 28, 28)

    def __init__(self):
        self.enc_dec = self.get_model()

    def get_data(self,db='mnist'):
        if db=='mnist':
            (x_train, y_train), (x_test, y_test) = mnist.load_data()
            (x_train, y_train), (x_test, y_test) = mnist.load_data()
            x_train = x_train.astype('float32') / 255.
            x_train = x_train.reshape((x_train.shape[0],) + self.original_img_size)
            x_test = x_test.astype('float32') / 255.
            x_test = x_test.reshape((x_test.shape[0],) + self.original_img_size)
            x_train[x_train < 0.5] = 0
            x_train[x_train >= 0.5] = 1
            x_test[x_test < 0.5] = 0
            x_test[x_test >= 0.5] = 1

            self.data = {
                'x_train': x_train,
                'y_train': y_train,
                'x_test': x_test,
                'y_test': y_test
            }
        else:
            raise AssertionError('db missing now')
        print('loading training data done')

    def get_model(self,interp=False):

        if interp:
            batch_size = self.cfg['batch_size']
            original_dim = np.prod(self.original_img_size)
            latent_dim = self.cfg['latent_dim']
            intermediate_dim = 256
            epsilon_std = 0.01

            x = Input(batch_shape=(batch_size, original_dim))
            h = Dense(intermediate_dim, activation='sigmoid')(x)
            z_mean = Dense(latent_dim)(h)
            z_log_var = Dense(latent_dim)(h)

            def sampling(args):
                z_mean, z_log_var = args
                epsilon = K.random_normal(shape=(batch_size, latent_dim), mean=0.,
                                          std=epsilon_std)
                return z_mean + K.exp(z_log_var / 2) * epsilon

            # note that "output_shape" isn't necessary with the TensorFlow backend
            z = Lambda(sampling, output_shape=(latent_dim,))([z_mean, z_log_var])

            # we instantiate these layers separately so as to reuse them later
            decoder_h = Dense(intermediate_dim, activation='sigmoid')
            decoder_mean = Dense(original_dim, activation='sigmoid')
            h_decoded = decoder_h(z)
            x_decoded_mean = decoder_mean(h_decoded)

            def vae_loss(x, x_decoded_mean):
                xent_loss = original_dim * objectives.binary_crossentropy(x, x_decoded_mean)
                kl_loss = - 0.5 * K.sum(1 + z_log_var - K.square(z_mean) - K.exp(z_log_var), axis=-1)
                return xent_loss + kl_loss

            vae = Model(x, x_decoded_mean)
            vae.compile(optimizer='adadelta', loss=vae_loss)
        else:
            batch_size = 100
            original_dim = 28 * 28
            latent_dim = 2
            # nb_epoch = 50

            if K.image_dim_ordering() == 'tf':
                x = Input(shape=(28, 28, 1))
            else:
                x = Input(shape=(1, 28, 28))
            # h = Flatten()(x)
            # x = Input(batch_shape=(batch_size, original_dim))
            # h = Reshape((1,28,28))(x)
            encode_h1 = Convolution2D(16, 3, 3, activation='relu', border_mode='same')
            encode_h2 = MaxPooling2D((2, 2), border_mode='same')
            encode_h3 = Convolution2D(32, 3, 3, activation='relu', border_mode='same')
            encode_h4 = MaxPooling2D((2, 2), border_mode='same')
            encode_h5 = Convolution2D(64, 3, 3, activation='relu', border_mode='same')
            encode_h6 = MaxPooling2D((2, 2), border_mode='same')

            h = encode_h1(x)
            h = encode_h2(h)
            h = encode_h3(h)
            h = encode_h4(h)
            h = encode_h5(h)
            h = encode_h6(h)

            h = Flatten()(h)
            z_mean = Dense(latent_dim)(h)
            z_log_var = Dense(latent_dim)(h)
            encoder = Model(x, z_mean)

            def sampling(args):
                z_mean, z_log_var = args
                epsilon = K.random_normal(shape=(batch_size, latent_dim), mean=0.)
                return z_mean + K.exp(z_log_var / 2) * epsilon

            # note that "output_shape" isn't necessary with the TensorFlow backend
            z = Lambda(sampling, output_shape=(latent_dim,))([z_mean, z_log_var])

            # we instantiate these layers separately so as to reuse them later

            decoder_h1 = Dense(64 * 4 * 4, activation='relu')
            if K.image_dim_ordering() == 'tf':
                decoder_h2 = Reshape((4, 4, 64))
            else:
                decoder_h2 = Reshape((64, 4, 4))
            decoder_h3 = Convolution2D(64, 3, 3, activation='relu', border_mode='same')
            decoder_h4 = UpSampling2D((2, 2))
            decoder_h5 = Convolution2D(32, 3, 3, activation='relu', border_mode='same')
            decoder_h6 = UpSampling2D((2, 2))
            decoder_h7 = Convolution2D(16, 3, 3, activation='relu', border_mode='same')
            decoder_h8 = UpSampling2D((2, 2))
            decoder_h9 = Convolution2D(1, 5, 5, activation='sigmoid', border_mode='valid')

            # g_input = Input(shape=[2])
            H = decoder_h1(z)
            H = decoder_h2(H)
            H = decoder_h3(H)
            H = decoder_h4(H)
            H = decoder_h5(H)
            H = decoder_h6(H)
            H = decoder_h7(H)
            H = decoder_h8(H)
            g_V = decoder_h9(H)

            # def g2b(g_V):
            #     '''grey value to binary'''
            #     return K.round(g_V)
            # g_V = Lambda(g2b, output_shape=g_V._keras_shape[1:4])(g_V)

            def vae_loss(x, g_V):
                xent_loss = original_dim * K.mean(objectives.binary_crossentropy(x, g_V))
                kl_loss = - 0.5 * K.sum(1 + z_log_var - K.square(z_mean) - K.exp(z_log_var), axis=-1)
                return xent_loss + kl_loss

            vae = Model(x, g_V)
            # keras.optimizers.RMSprop(lr=0.001, rho=0.9, epsilon=1e-08, decay=0.0)
            vae.compile(optimizer='rmsprop', loss=vae_loss)

            vae.summary()


            return vae

    def train_vae(self):
        x_train = self.data['x_train']
        x_test = self.data['x_test']
        self.enc_dec.fit(x_train, x_train,
                shuffle=True,
                nb_epoch=self.cfg['max_epochs'],
                batch_size=self.cfg['batch_size'],
                validation_data=(x_test, x_test))

    def encoder(self):
        # load from trained vae model
        x = Input(shape=self.original_img_size)
        h = x
        for i in range(1,9):
            h = self.enc_dec.layers[i](h)

        return Model(x, h)

    def decoder(self):
        # load from trained vae model
        x = Input(shape=(self.cfg['latent_dim'],))
        h = x
        for i in range(11,20):
            h = self.enc_dec.layers[i](h)
        return Model(x, h)

    def input2latent(self):
        # display a 2D plot of the digit classes in the latent space
        encoder = vae.encoder()
        x_test_encoded = encoder.predict(self.data['x_test'], batch_size=self.data['batch_size'])
        plt.figure(figsize=(6, 6))
        plt.scatter(x_test_encoded[:, 0], x_test_encoded[:, 1], c=self.data['y_test'])
        plt.colorbar()
        plt.show()

    def latent2output(self):
        # display a 2D manifold of the digits
        n = 15  # figure with 15x15 digits
        digit_size = 28
        figure = np.zeros((digit_size * n, digit_size * n))
        # we will sample n points within [-15, 15] standard deviations
        grid_x = np.linspace(-0.2, 0.2, n)
        grid_y = np.linspace(-0.2, 0.2, n)

        decoder = vae.decoder()
        for i, yi in enumerate(grid_x):
            for j, xi in enumerate(grid_y):
                z_sample = np.array([[xi, yi]])
                x_decoded = decoder.predict(z_sample)
                digit = x_decoded[0].reshape(digit_size, digit_size)
                figure[i * digit_size: (i + 1) * digit_size,
                j * digit_size: (j + 1) * digit_size] = digit

        plt.figure(figsize=(10, 10))
        plt.imshow(figure)
        plt.show(block=True)

    def reconstruction(self):
        dec = self.decoder()
        enc = self.encoder()
        n = 20
        data = self.data['x_train'][0:n]
        enc_x = enc.predict(data)
        rec_x = dec.predict(enc_x)

        plt.figure(figsize=(20, 4))
        for i in range(n):
            # display original
            ax = plt.subplot(2, n, i+1)
            plt.imshow(data[i].reshape(28, 28), cmap='Greys',interpolation='nearest')
            ax.get_xaxis().set_visible(False)
            ax.get_yaxis().set_visible(False)
            ax = plt.subplot(2, n, i + n+1)

            # display reconstruction
            plt.imshow(rec_x[i].reshape(28, 28), cmap='Greys',interpolation='nearest')
            ax.get_xaxis().set_visible(False)
            ax.get_yaxis().set_visible(False)
        plt.show()
        return rec_x

    def saliency(self):
        '''get saliency info'''
        y_train = self.data['y_train']
        oneidx = np.where(y_train == 1)
        rmnist_train = np.zeros((oneidx[0].shape[0], self.cfg['input_dim'][0], self.cfg['input_dim'][1], 1))
        bmnist_train = np.zeros((oneidx[0].shape[0], self.cfg['input_dim'][0], self.cfg['input_dim'][1], 1))
        for idx,idxx in enumerate(oneidx[0]):
            data = self.data['x_train'] [idxx,:,:,0] # only one channel
            cmax = 1.0
            for ypos in range(28):
                if (data[ypos] == 1).any():
                    d = ypos
                    break
            for ypos in range(d, 28):
                if (data[ypos] == 1).any():
                    xpos = np.where(data[ypos] == 1)
                    tmp = cmax - 10.0/255.0 * (ypos - d)
                    for jdx in xpos[0]:
                        rmnist_train[idx,ypos,jdx,0] = tmp
                        bmnist_train[idx,ypos,jdx,0] = 1

        y_test = self.data['y_test']
        oneidx = np.where(y_test == 1)
        rmnist_test = np.zeros((oneidx[0].shape[0], self.cfg['input_dim'][0], self.cfg['input_dim'][1], 1))
        bmnist_test = np.zeros((oneidx[0].shape[0], self.cfg['input_dim'][0], self.cfg['input_dim'][1], 1))
        for idx,idxx in enumerate(oneidx[0]):
            data = self.data['x_test'] [idxx,:,:,0] # only one channel
            cmax = 1.0
            for ypos in range(28):
                if (data[ypos] == 1).any():
                    d = ypos
                    break
            for ypos in range(d, 28):
                if (data[ypos] == 1).any():
                    xpos = np.where(data[ypos] == 1)
                    tmp = cmax - 10.0/255.0 * (ypos - d)
                    for jdx in xpos[0]:
                        rmnist_test[idx,ypos,jdx,0] = tmp
                        bmnist_test[idx,ypos,jdx,0] = 1
        return{
            'bmnist_train': bmnist_train,
            'bmnist_test': bmnist_test,
            'rmnist_train': rmnist_train,
            'rmnist_test': rmnist_test
        }


    def sal_dec(self):
        data = self.saliency()

        sal = self.decoder()
        sal.compile(optimizer='rmsprop', loss='binary_crossentropy')
        sal.summary()

        encoder = self.encoder()
        enc_x_train = encoder.predict(data['bmnist_train'])
        enc_x_test = encoder.predict(data['bmnist_test'])

        sal.fit(enc_x_train, data['rmnist_train'],
                 shuffle=True,
                 nb_epoch=self.cfg['max_epochs'],
                 batch_size=self.cfg['batch_size'],
                 validation_data=(enc_x_test, data['rmnist_test']))

        n = 5
        binput = data['bmnist_train'][0:n,:,:,:]
        routput = sal.predict(encoder.predict(binput))
        plt.figure(figsize=(20, 4))
        for i in range(n):
            # display original
            ax1 = plt.subplot(2, n, i + 1)
            plt.imshow(binput[i,:,:,0].reshape(28, 28),cmap='Greys',interpolation='nearest')
            ax1.get_xaxis().set_visible(False)
            ax1.get_yaxis().set_visible(False)
            # display sal prediction
            ax2 = plt.subplot(2, n, i + 1 + n)
            plt.imshow(routput[i,:,:,0].reshape(28, 28),cmap='Greys',interpolation='nearest')
            ax2.get_xaxis().set_visible(False)
            ax2.get_yaxis().set_visible(False)
        plt.show(block=True)

        binput = data['bmnist_test'][0:n, :, :, :]
        routput = sal.predict(encoder.predict(binput))
        plt.figure(figsize=(20, 4))
        for i in range(n):
            # display original
            ax1 = plt.subplot(2, n, i + 1)
            plt.imshow(binput[i, :, :, 0].reshape(28, 28), cmap='Greys',interpolation='nearest')
            ax1.get_xaxis().set_visible(False)
            ax1.get_yaxis().set_visible(False)
            # display sal prediction
            ax2 = plt.subplot(2, n, i + 1 + n)
            plt.imshow(routput[i, :, :, 0].reshape(28, 28), cmap='Greys',interpolation='nearest')
            ax2.get_xaxis().set_visible(False)
            ax2.get_yaxis().set_visible(False)
        plt.show(block=True)

if 1:
    vae = VAE()
    vae.get_data()
    vae.train_vae()
    #
    #
    # plot(vae.enc_dec, to_file='model.png')
    # vae.enc_dec.save('enc_dec.h5')  # creates a HDF5 file 'my_model.h5'
    #
    vae.reconstruction()

    vae.sal_dec()

else:
    vae = VAE()
    vae.get_data()

    load_model('my_model.h5')
    vae.enc = vae.encoder()
    vae.dec = vae.decoder()

    vae.latent2output()

    vae.reconstruction()


