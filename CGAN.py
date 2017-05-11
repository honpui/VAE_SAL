# TO DO:
# Add tensorflow image monitoring
# load data in batch to reduce gpu memory consumption
# added Enc(Dec(x)), but need Dec(z)

# add batch norm in vae
# consider dropout to improve GAN
# consider flip labels to relief gradient vanishing
# consider use PID to balance D and G loss
# try inception in vae
# Maybe pre-train GAN using VAE?
# crossentropy loss v.s. l1 norm in VAE loss?


# problem:
# x_rec ranging from 0.1 to about 0.5, not sure why

import tensorflow as tf
from tqdm import tqdm
import os
import dateutil.tz
import datetime
import math
import numpy as np
from PIL import Image
import json
import sys
# import prettytensor as pt

slim = tf.contrib.slim
TINY = 1e-8

def plt_rec(x_test, x_rec):
            import matplotlib.pyplot as plt
            n = 10
            plt.figure(figsize=(20, 4))
            for i in range(n):
                # display original
                ax = plt.subplot(2, n, i + 1)
                plt.imshow(x_test[i].reshape(64, 64, 3))
                ax.get_xaxis().set_visible(False)
                ax.get_yaxis().set_visible(False)
                ax = plt.subplot(2, n, i + n + 1)

                # display reconstruction
                plt.imshow(x_rec[i].reshape(64, 64, 3))
                ax.get_xaxis().set_visible(False)
                ax.get_yaxis().set_visible(False)
            plt.show()

def make_grid(tensor, nrow=8, padding=2,
              normalize=False, scale_each=False):
    """Code based on https://github.com/pytorch/vision/blob/master/torchvision/utils.py"""
    nmaps = tensor.shape[0]
    xmaps = min(nrow, nmaps)
    ymaps = int(math.ceil(float(nmaps) / xmaps))
    height, width = int(tensor.shape[1] + padding), int(tensor.shape[2] + padding)
    grid = np.zeros([height * ymaps + 1 + padding // 2, width * xmaps + 1 + padding // 2, 3], dtype=np.uint8)
    k = 0
    for y in range(ymaps):
        for x in range(xmaps):
            if k >= nmaps:
                break
            h, h_width = y * height + 1 + padding // 2, height - padding
            w, w_width = x * width + 1 + padding // 2, width - padding

            grid[h:h+h_width, w:w+w_width] = tensor[k]
            k = k + 1
    return grid

def save_image(tensor, filename, nrow=8, padding=2,
               normalize=False, scale_each=False):
    """code from on BEGAN"""
    ndarr = make_grid(tensor, nrow=nrow, padding=padding,
                            normalize=normalize, scale_each=scale_each)
    im = Image.fromarray(ndarr)
    im.save(filename)

def save_config(config, model_dir):
    """code from BEGAN"""
    param_path = os.path.join(model_dir, "params.txt")
    json.dump(config, open(param_path , 'w'))

def to_nhwc(image, data_format):
    if data_format == 'NCHW':
        new_image = nchw_to_nhwc(image)
    else:
        new_image = image
    return new_image

def norm_img(image, data_format=None):
    image = image/127.5 - 1.
    if data_format:
        image = to_nhwc(image, data_format)
    return image

def int_shape(tensor):
    shape = tensor.get_shape().as_list()
    return [num if num is not None else -1 for num in shape]

def nchw_to_nhwc(x):
    return tf.transpose(x, [0, 2, 3, 1])

def nhwc_to_nchw(x):
    return tf.transpose(x, [0, 3, 1, 2])

def get_conv_shape(tensor, data_format):
    shape = int_shape(tensor)
    # always return [N, H, W, C]
    if data_format == 'NCHW':
        return [shape[0], shape[2], shape[3], shape[1]]
    elif data_format == 'NHWC':
        return shape

def resize_nearest_neighbor(x, new_size, data_format):
    if data_format == 'NCHW':
        x = nchw_to_nhwc(x)
        x = tf.image.resize_nearest_neighbor(x, new_size)
        x = nhwc_to_nchw(x)
    else:
        x = tf.image.resize_nearest_neighbor(x, new_size)
    return x

def upscale(x, scale, data_format):
    _, h, w, _ = get_conv_shape(x, data_format)
    return resize_nearest_neighbor(x, (h*scale, w*scale), data_format)

def reshape(x, h, w, c, data_format):
    if data_format == 'NCHW':
        x = tf.reshape(x, [-1, c, h, w])
    else:
        x = tf.reshape(x, [-1, h, w, c])
    return x

class GAN4(object):
    def activation(self, cfg):
        '''define activation function of the convolution'''
        if cfg['act_func'] == 'ELU':
            alpha = 1.0,  # ELU
            return tf.nn.elu
        elif cfg['act_func'] == 'ReLu':
            alpha = 0.3,  # LeakyReLu
            return tf.nn.relu
        else:
            raise NameError('Not supported activation function type')

    def CelebA(self, datadir, num=200000):
        '''load human face dataset'''
        import h5py
        from random import sample
        import numpy as np
        f = h5py.File(datadir+"/celeba.hdf5", "r")
        data_key = f.keys()[0]
        data = (np.asarray(f[data_key],dtype='float32') / 255. - 0.5 )*2 # normalized into (-1, 1)
        # data = np.asarray(f[data_key],dtype='float32') / 255.
        # data = data.transpose((0,2,3,1))
        label_key = f.keys()[1]
        label = np.asarray(f[label_key])

        split = 0.1
        l = len(data)  # length of data
        n1 = int(split * l)  # split for testing
        indices = sample(range(l), n1)

        x_test = data[indices]
        y_test = label[indices]
        x_train = np.delete(data, indices, 0)
        y_train = np.delete(label, indices, 0)

        # return (x_train, y_train), (x_test, y_test)
        return (x_train[0:num], y_train[0:num]), (x_test[0:1000], y_test[0:1000])

    def sampling(self, z_mean, z_log_var ):
        epsilon = tf.random_normal(shape=(self.batch_size, self.latent_dim), mean=0.)
        return z_mean + tf.exp(z_log_var / 2) * epsilon

    def creat_dir(self,network_type):
        """code from on InfoGAN"""
        now = datetime.datetime.now(dateutil.tz.tzlocal())
        timestamp = now.strftime('%Y_%m_%d_%H_%M_%S')
        root_log_dir = "logs/" + network_type
        exp_name = network_type + "_%s" % timestamp
        log_dir = os.path.join(root_log_dir, exp_name)

        now = datetime.datetime.now(dateutil.tz.tzlocal())
        timestamp = now.strftime('%Y_%m_%d_%H_%M_%S')
        root_model_dir = "models/" + network_type
        exp_name = network_type + "_%s" % timestamp
        model_dir = os.path.join(root_model_dir, exp_name)

        for path in [log_dir, model_dir]:
            if not os.path.exists(path):
                os.makedirs(path)
        return log_dir, model_dir

    def encoder(self, input, n_blocks, encoder_module):

        with tf.variable_scope("encoder", reuse=True):
            output = input
            for block_i in range(n_blocks):
                n_ch = self.n_filter * 2 ** block_i
                output = encoder_module(output, n_ch)

            # FC layers
            h1 = slim.flatten(output)
            if self.network_type == 'AE':
                h2 = slim.fully_connected(h1, self.latent_dim, activation_fn=None)
                output = h2
            else:
                h2 = slim.fully_connected(h1, 2 * self.latent_dim,
                                          activation_fn=None)  # doubled for both mean and variance
                self.z_mean, self.z_log_var = tf.split(h2, num_or_size_splits=2, axis=1)
                output = self.sampling(self.z_mean, self.z_log_var)

        return output

    def decoder(self, h, n_blocks, decoder_module):

        with tf.variable_scope("decoder", reuse=True):
            iterm_size = self.img_size / 2 ** n_blocks
            iterm_ch = self.n_filter * 2 ** (n_blocks - 1)
            h3 = slim.fully_connected(h, iterm_size * iterm_size * iterm_ch, activation_fn=None)
            h = tf.reshape(h3, [self.batch_size, iterm_size, iterm_size, iterm_ch])

            output = h
            for block_i in range(n_blocks,0,-1):
                n_ch = self.n_filter*2**(block_i-1)
                output = decoder_module(output, n_ch)
            # initializer = tf.truncated_normal_initializer(stddev=0.01)
            # regularizer = slim.l2_regularizer(0.0005)
            output = slim.conv2d_transpose(output, self.n_ch_in, (3, 3), activation_fn=None, scope='this')#, padding='same'
        return output

    def Incep_enc_block(self, input, n_ch, act_func):
        output1 = slim.conv2d(input, n_ch, 1, 2, activation_fn=act_func)

        output2 = slim.conv2d(input, n_ch, 1, 1, activation_fn=act_func)
        output2 = slim.conv2d(output2, n_ch, 3, 2, activation_fn=act_func) #scope='conv3_1'

        # output3 = slim.conv2d(input, n_ch, 1, 1, activation_fn=self.act_func)
        # output3 = slim.conv2d(output3, n_ch, 3, 1, activation_fn=self.act_func)
        # output3 = slim.conv2d(output3, n_ch, 3, 2, activation_fn=self.act_func) #scope='conv3_1'

        output = tf.concat(axis=3, values=[output1, output2])
        return output

    def Incep_dec_block(self, input, n_ch, act_func):
        output1 = slim.conv2d_transpose(input, n_ch, 1, 2, activation_fn=act_func)

        output2 = slim.conv2d_transpose(input, n_ch, 1, 1, activation_fn=act_func)
        output2 = slim.conv2d_transpose(output2, n_ch, 3, 2, activation_fn=act_func) #scope='conv3_1'

        # output3 = slim.conv2d_transpose(input, n_ch, 1, 1, activation_fn=self.act_func)
        # output3 = slim.conv2d_transpose(output3, n_ch, 3, 1, activation_fn=self.act_func)
        # output3 = slim.conv2d_transpose(output3, n_ch, 3, 2, activation_fn=self.act_func) #scope='conv3_1'

        output = tf.concat(axis=3, values=[output1, output2])
        return output

    def VGG_enc_block(self, input, n_ch, act_func):
        '''convolution module for encoder'''
        initializer = tf.truncated_normal_initializer(stddev=0.01)
        regularizer = slim.l2_regularizer(0.0005)
        output = slim.conv2d(input, n_ch, 3, 1, activation_fn=act_func)
        output = slim.conv2d(output, n_ch, 3, 2, activation_fn=act_func) #scope='conv3_1'
        return output

    def VGG_dec_block(self, input, n_ch, act_func):
        '''convolution module for decoder'''
        initializer = tf.truncated_normal_initializer(stddev=0.01)
        regularizer = slim.l2_regularizer(0.0005)
        output = slim.conv2d_transpose(input, n_ch, 3, 1, activation_fn=act_func)
        output = slim.conv2d_transpose(output, n_ch, 3, 2, activation_fn=act_func) #scope='conv3_1'
        return output

    def BEGAN_enc(self,input, act_func, hidden_num = 128, z_num = 64, repeat_num = 4, data_format = 'NCHW', reuse = False):

        # Encoder
        x = slim.conv2d(input, hidden_num, 3, 1, activation_fn=act_func, data_format=data_format)

        prev_channel_num = hidden_num
        for idx in range(repeat_num):
            channel_num = hidden_num * (idx + 1)
            x = slim.conv2d(x, channel_num, 3, 1, activation_fn=act_func, data_format=data_format)
            x = slim.conv2d(x, channel_num, 3, 1, activation_fn=act_func, data_format=data_format)
            if idx < repeat_num - 1:
                # x = slim.conv2d(x, channel_num, 3, 2, activation_fn=tf.nn.elu, data_format=data_format)
                x = tf.contrib.layers.max_pool2d(x, [2, 2], [2, 2], padding='VALID', data_format=data_format)

        x = tf.reshape(x, [-1, np.prod([8, 8, channel_num])])
        z = x = slim.fully_connected(x, z_num, activation_fn=None)
        return z

    def BEGAN_dec(self,input,hidden_num ,act_func, input_channel = 3, data_format = 'NCHW', repeat_num = 4):

        # Decoder
        x = slim.fully_connected(input, np.prod([8, 8, hidden_num]), activation_fn=None)
        x = reshape(x, 8, 8, hidden_num, data_format)

        for idx in range(repeat_num):
            x = slim.conv2d(x, hidden_num, 3, 1, activation_fn=act_func, data_format=data_format)
            x = slim.conv2d(x, hidden_num, 3, 1, activation_fn=act_func, data_format=data_format)
            if idx < repeat_num - 1:
                x = upscale(x, 2, data_format)

        out = slim.conv2d(x, input_channel, 3, 1, activation_fn=None, data_format=data_format)

        return out

    def __init__(self,cfg):
        self.log_vars = []

        self.variational = cfg['vae']
        self.datadir = cfg['datadir']
        self.gamma = tf.cast(cfg['gamma'], tf.float32)
        self.lambda_k = tf.cast(cfg['lambda_k'], tf.float32)
        self.k_t = tf.Variable(0., trainable=False, name='k_t')

        if self.variational:
            self.network_type = 'VAE'
        else:
            self.network_type = 'AE'
        self.logdir, self.modeldir = self.creat_dir('GAN')
        save_config(cfg, self.modeldir)

        # Network parameters for GAN
        self.epochs = cfg['max_epochs']
        self.d_lr = cfg['d_lr']
        self.g_lr = cfg['g_lr']
        self.g_optimizer = tf.train.AdamOptimizer(self.g_lr)
        if cfg['d_optimizer'] == 'adam':
            self.d_optimizer = tf.train.AdamOptimizer(self.d_lr)
        elif cfg['d_optimizer'] == 'adadelta':
            self.d_optimizer = tf.train.AdadeltaOptimizer(self.d_lr)
        elif cfg['d_optimizer'] == 'adagrad':
            self.d_optimizer = tf.train.AdagradOptimizer(self.d_lr)
        else:
            raise Exception("[!] Caution! {} opimizer is not implemented in VAE training".format(self.optimizer))


        if cfg['pre_train']:
            self.vae_g.train_vae(epochs=cfg['pre_train'])
            self.vae_d.train_vae(epochs=cfg['pre_train'])

        # # Network Parameter Setting
        self.variational = cfg['vae']
        self.act_func = self.activation(cfg)
        self.latent_dim = cfg['latent_dim']
        self.n_filter = cfg['n_filters']
        self.filter_size = cfg['filter_size']
        self.img_size = cfg['input_dim'][0]
        self.n_ch_in = cfg['n_channels']
        self.n_attributes = cfg['n_attributes']
        # self.datadir = cfg['datadir']
        # self.encoder_module = self.VGG_enc_block
        # self.decoder_module = self.VGG_dec_block
        self.n_blocks = cfg['n_blocks']
        # define VAE network
        # Optimizer Parameter Setting
        self.batch_size = cfg['batch_size']
        self.optimizer = cfg['vae_optimizer']
        self.vae_lr = cfg['vae_lr']
        self.snapshot_interval = cfg['snapshot_interval']

        from data_loader import get_loader
        data_path = '/home/hope-yao/Documents/Data/img_align_celeba'
        batch_size = 16
        input_scale_size = 64
        data_format = 'NCHW'
        split = 'train'
        self.data_loader = get_loader(
            data_path, batch_size, input_scale_size,
            data_format, split)
        # self.x_input = self.data_loader
        # self.y_input = tf.zeros([self.batch_size, self.n_attributes])
        # self.z_input = tf.random_uniform(
        #     (self.batch_size, self.latent_dim), minval=-1.0, maxval=1.0)
        self.x_input = tf.placeholder(tf.float32, [self.batch_size, self.n_ch_in, self.img_size, self.img_size])
        self.y_input = tf.placeholder(tf.float32, [self.batch_size, self.n_attributes])
        self.z_input = tf.placeholder(tf.float32, [self.batch_size, self.latent_dim], name='z_input')

    def train_gan(self, **kwargs):
        '''model training'''

        # (self.X_train, self.y_train), (self.X_test, self.y_test) = self.vae_g.CelebA(self.vae_g.datadir)
        # x_gen, self.G_var = self.GeneratorCNN(z, conv_hidden_num, channel,repeat_num, data_format, reuse=False)
        # d_out, self.D_z, self.D_var = self.DiscriminatorCNN(tf.concat([x_gen, x], 0), channel, z_num,
        #                                                     repeat_num,conv_hidden_num, data_format)
        with tf.variable_scope("G") as vs_g:
            x_gen = self.BEGAN_dec(self.z_input, hidden_num=128 ,act_func=self.act_func, input_channel=3, data_format='NCHW', repeat_num=4)
        self.G_var = tf.contrib.framework.get_variables(vs_g)
        with tf.variable_scope("D") as vs_d:
            x = norm_img(self.x_input)
            z_d = self.BEGAN_enc(tf.concat([x_gen, x], 0), act_func=self.act_func, hidden_num = 128, z_num = 64, repeat_num = 4, data_format = 'NCHW', reuse = False)
            d_out = self.BEGAN_dec(z_d, hidden_num=128 ,act_func=self.act_func, input_channel=3, data_format='NCHW', repeat_num=4)
            x_gen_rec, x_rec = tf.split(d_out, 2)
        self.D_var = tf.contrib.framework.get_variables(vs_d)

        self.x_rec, self.x_gen, self.x_gen_rec = x_rec, x_gen, x_gen_rec
        g_optimizer, d_optimizer = tf.train.AdamOptimizer(self.g_lr), tf.train.AdamOptimizer(self.d_lr)

        self.d_loss_real = tf.reduce_mean(tf.abs(x_rec - x))
        self.d_loss_fake = tf.reduce_mean(tf.abs(x_gen_rec - x_gen))

        self.d_loss = self.d_loss_real - self.k_t * self.d_loss_fake
        self.g_loss = tf.reduce_mean(tf.abs(x_gen_rec - x_gen))
        self.balance = self.gamma * self.d_loss_real - self.g_loss
        self.measure = self.d_loss_real + tf.abs(self.balance)

        self.step = tf.Variable(0, name='step', trainable=False)
        d_optim = d_optimizer.minimize(self.d_loss, var_list=self.D_var)
        g_optim = g_optimizer.minimize(self.g_loss, global_step=self.step, var_list=self.G_var)
        with tf.control_dependencies([d_optim, g_optim]):
            self.k_update = tf.assign(
                self.k_t, tf.clip_by_value(self.k_t + self.lambda_k * self.balance, 0, 1))
        for k, v in self.log_vars:
            tf.summary.scalar(k, v)
        self.summary_op = tf.summary.merge([
            tf.summary.scalar("loss/d_loss", self.d_loss),
            tf.summary.scalar("loss/d_loss_real", self.d_loss_real),
            tf.summary.scalar("loss/d_loss_fake", self.d_loss_fake),
            tf.summary.scalar("loss/g_loss", self.g_loss),
            tf.summary.scalar("misc/measure", self.measure),
            tf.summary.scalar("misc/k_t", self.k_t),
            tf.summary.scalar("misc/d_lr", self.d_lr),
            tf.summary.scalar("misc/g_lr", self.g_lr),
            tf.summary.scalar("misc/balance", self.balance),
        ])
        summary_writer = tf.summary.FileWriter(self.logdir)
        saver = tf.train.Saver()

        self.step = tf.Variable(0, name='step', trainable=False)
        sv = tf.train.Supervisor(
                                logdir=self.logdir,
                                is_chief=True,
                                saver=saver,
                                summary_op=None,
                                summary_writer=summary_writer,
                                save_model_secs=300,
                                global_step=self.step,
                                ready_for_local_init_op=None)

        gpu_options = tf.GPUOptions(allow_growth=True)
        # gpu_options = tf.GPUOptions(per_process_gpu_memory_fraction=0.3)
        sess_config = tf.ConfigProto(allow_soft_placement=True,
                                    gpu_options=gpu_options)
        sess = sv.prepare_or_wait_for_session(config=sess_config)
        x_fixed = self.data_loader.eval(session=sess)
        y_fixed = np.zeros([self.batch_size, self.n_attributes])
        z_fixed = np.random.uniform(-1, 1, size=(self.batch_size, self.latent_dim))
        feed_dict_fix = {self.x_input: x_fixed, self.y_input: y_fixed, self.z_input: z_fixed}

        counter = 0
        for i in tqdm(range(self.epochs)):  # 1875 * 32 = 60000 -> # of training samples
            counter += 1
            x_input = self.data_loader
            y_input = np.zeros([self.batch_size, self.n_attributes])
            z_input = np.random.uniform(-1, 1, size=(self.batch_size, self.latent_dim)).astype('float32')
            feed_dict = {self.x_input: x_input.eval(session=sess), self.y_input: y_input, self.z_input:z_input}
            result = sess.run([self.d_loss,self.g_loss,self.measure,self.k_update,self.k_t],feed_dict)
            print(result)

            if counter % (10*self.snapshot_interval) == 0:
                x_train, x_rec_img, x_rec_rec_img, x_gen_img, x_gen_rec_img =\
                    sess.run([self.x_input, self.x_rec, self.x_rec_rec, self.x_gen,self.x_gen_rec], feed_dict_fix)
                nrow = 12
                all_G_z = np.concatenate([x_train[0:nrow].transpose((0,2,3,1)),
                                          255 * (x_rec_img[0:nrow].transpose((0, 2, 3, 1)) + 1) / 2,
                                          255 * (x_rec_rec_img[0:nrow].transpose((0, 2, 3, 1)) + 1) / 2,
                                          255 * (x_gen_img[0:nrow].transpose((0,2,3,1)) + 1) / 2,
                                          255 * (x_gen_rec_img[0:nrow].transpose((0,2,3,1)) + 1) / 2])
                save_image(all_G_z, '{}/itr{}.png'.format(self.logdir, i),nrow=nrow)

        # (self.X_train, self.y_train), (self.X_test, self.y_test) = self.CelebA(self.datadir)
        # for epoch in range(self.epochs):
        #     it_per_ep = len(self.X_train) / self.batch_size
        #     for i in tqdm(range(it_per_ep)):
        #         x_input = self.X_train[i * self.batch_size:(i + 1) * self.batch_size]
        #         y_input = self.y_train[i * self.batch_size:(i + 1) * self.batch_size]
        #         z_input = np.random.uniform(-1, 1, size=(self.batch_size, self.latent_dim)).astype('float32')
        #         feed_dict = {self.x_input: x_input, self.y_input: y_input, self.z_input: z_input}
        #         result = sess.run([self.d_loss, self.g_loss, self.measure, self.k_update, self.k_t], feed_dict)
        #         print(result)
        #         if counter % (10 * self.snapshot_interval) == 0:
        #             x_train, x_rec_img, x_rec_rec_img, x_gen_img, x_gen_rec_img = \
        #                 sess.run([self.x_input, self.x_rec, self.x_rec_rec, self.x_gen, self.x_gen_rec], feed_dict_fix)
        #             nrow = 12
        #             all_G_z = np.concatenate([x_train[0:nrow].transpose((0, 2, 3, 1)),
        #                                       255 * (x_rec_img[0:nrow].transpose((0, 2, 3, 1)) + 1) / 2,
        #                                       255 * (x_rec_rec_img[0:nrow].transpose((0, 2, 3, 1)) + 1) / 2,
        #                                       255 * (x_gen_img[0:nrow].transpose((0, 2, 3, 1)) + 1) / 2,
        #                                       255 * (x_gen_rec_img[0:nrow].transpose((0, 2, 3, 1)) + 1) / 2])
        #             save_image(all_G_z, '{}/itr{}.png'.format(self.logdir, i), nrow=nrow)

if __name__ == "__main__":

    cfg = {'batch_size': 16,
           'n_blocks': 4,  # there are n_blocks convolution and pooling structure
            'act_func': 'ELU', #ELU, ReLu
           'input_dim': (64, 64),
           'n_channels': 3,
           'n_attributes': 40,
           'n_filters': 32,
           'filter_size': (3,3),
           'max_epochs': 200000,
           'latent_dim': 64,
           'vae_optimizer': 'adadelta',
           'vae_lr': 8e-1,
           'g_lr': 0.00008,
           'd_lr': 0.00008,
           'g_optimizer': 'adam',
           'd_optimizer': 'adam',
           'gamma': 0.5,
           'lambda_k': 0.001,
           'k_t': 0.0,
           # 'learning_rate': lr_schedule,
           'vae': False,
           'datadir': '/home/hope-yao/Documents/Data',
           'pre_train': 0, # how many steps to pretrain the VAE
           'snapshot_interval': 500,
           }

    # vae = VAE(cfg)
    # vae.train_vae()

    gan = GAN4(cfg)
    gan.train_gan()