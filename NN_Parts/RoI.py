from Debugger import DebugPrint
import numpy as np
import tensorflow as tf
from NN_Parts import Backbone
from FasterRCNN_config import Param

class RoI:
    def __init__(self, backbone_model, IMG_SHAPE, n_stage= 5):
        self.base_model = backbone_model
        proposal_boxes = tf.keras.Input(shape=(4,),batch_size = None,name='PROPOSAL_BOXES')
        shape1 = tf.shape(proposal_boxes)
        n_boxes = tf.gather_nd(shape1, [0])
        indices = tf.range(start=0, limit=n_boxes, dtype=tf.int32)
        img_shape_constant = tf.constant([IMG_SHAPE[0], IMG_SHAPE[1], IMG_SHAPE[0], IMG_SHAPE[1]], tf.float32)
        proposal_boxes2 = tf.math.divide(proposal_boxes, img_shape_constant)



        image_crop = tf.image.crop_and_resize(self.base_model.output, proposal_boxes2,indices, [6,6])
        flatten1 = tf.keras.layers.GlobalAveragePooling2D()(image_crop)
        fc1 = tf.keras.layers.Dense(units=1024, activation='relu')(flatten1)
        # fc2 = tf.keras.layers.Dense(units=2048, activation='relu')(fc1)
        class_header = tf.keras.layers.Dense(units=81, activation='softmax')(fc1)
        box_reg_header = tf.keras.layers.Dense(units=4, activation='linear')(fc1)

        self.RoI_train_model = tf.keras.Model(inputs=[self.base_model.input, proposal_boxes], outputs=[class_header, box_reg_header])
        # self.RoI_train_model.compile(optimizer=tf.keras.optimizers.Adam(learning_rate=Param.LR),
        #                              loss=['sparse_categorical_crossentropy','huber_loss'], loss_weights=[1,10])
        tf.keras.utils.plot_model(self.RoI_train_model, 'RoI_with_backbone.png', show_shapes=True)

        # --- for train step ---
        self.huber = tf.keras.losses.Huber()
        self.optimizer = tf.keras.optimizers.Adam(1e-4)


    @tf.function
    def train_step(self, input_image, proposal_box, class_header, box_reg_header):
        with tf.GradientTape() as RoI_tape:
            class_pred, box_reg_pred = self.RoI_train_model([input_image, proposal_box])
            class_loss = tf.keras.losses.sparse_categorical_crossentropy(y_true=class_header, y_pred=class_pred)

            box_reg_loss = self.huber(y_true=box_reg_header, y_pred=box_reg_pred)
            total_loss = tf.reduce_mean(tf.add(class_loss, box_reg_loss))
        gradients = RoI_tape.gradient(total_loss, self.RoI_train_model.trainable_variables)
        self.optimizer.apply_gradients(zip(gradients, self.RoI_train_model.trainable_variables))





if __name__=='__main__':
    b1 = Backbone()
    t1 = RoI(b1.backbone_model,IMG_SHAPE=(720,1280,3))

