import json
import numpy as np
import cv2 as cv
import matplotlib.pyplot as plt
from Data_Helper import coco_tools
import random
from NN_Helper import bbox_tools, gen_candidate_anchors
import tensorflow as tf



class NN_data_generator():
    def __init__(self, file, imagefolder_path, img_shape=(720,1280), n_stage=5):
        self.dataset_coco = coco_tools(file, imagefolder_path)
        self.anchor_generator = gen_candidate_anchors(img_shape=img_shape, n_stage=n_stage)

    def gen_train_target(self, image_id, debuginfo=False):
        bboxes = self.dataset_coco.GetOriginalBboxesList(image_id=image_id)

        bboxes_ious = []    # for each gt_bbox calculate ious with candidates
        for bbox in bboxes:
            ious = bbox_tools.ious(self.anchor_generator.anchor_candidates_list, bbox)
            ious_temp = np.ones(shape=(len(ious)), dtype=np.float) * 0.5
            # other author's implementations are use -1 to indicate ignoring, here use 0.5 to use max
            ious_temp = np.where(np.asarray(ious)>0.7, 1, ious_temp)
            ious_temp = np.where(np.asarray(ious)<0.3, 0, ious_temp)
            ious_temp[np.argmax(ious)] = 1
            bboxes_ious.append(ious_temp)

        # for each candidate anchor, determine the anchor target
        anchors_target = np.array(bboxes_ious)
        anchors_target = np.max(anchors_target, axis=0)
        anchors_target = np.reshape(anchors_target, newshape=(self.anchor_generator.h, self.anchor_generator.w, self.anchor_generator.n_anchors))
        if debuginfo:
            print(f"[Debug INFO] Number of total gt bboxes :{len(bboxes)}")
            print(f"[Debug INFO] Number of total target anchors: {anchors_target[np.where(anchors_target==1)].shape[0]}")
            print(f"[Debug INFO] Shape of anchors_target: {anchors_target.shape}")
            print(f"[Debug INFO] Selected anchors: \n {self.anchor_generator.anchor_candidates[np.where(anchors_target == 1)]}")
        # test
        # self.anchor_generator.anchors_candidate[np.where(anchors_target==1)] = self.anchor_generator.anchors_candidate[np.where(anchors_target==1)] +100
        # print(f"Selected anchors: \n {self.anchor_generator.anchors_candidate[np.where(anchors_target == 1)]}")

        # for each gt_box, determine the box reg target
        bbox_reg_target = np.zeros(shape=(self.anchor_generator.h, self.anchor_generator.w, self.anchor_generator.n_anchors, 4), dtype=np.float)
        for index, bbox_ious in enumerate(bboxes_ious):
            ious_temp = np.reshape(bbox_ious, newshape=(self.anchor_generator.h, self.anchor_generator.w, self.anchor_generator.n_anchors))
            gt_box = bboxes[index]
            candidate_boxes = self.anchor_generator.anchor_candidates[np.where(ious_temp == 1)]
            # print(candidate_boxes,gt_box)
            box_reg = bbox_tools.bbox_regression_target(candidate_boxes, gt_box)
            # print(box_reg)
            # print(bbox_tools.bbox_reg2truebox(candidate_boxes, box_reg))
            bbox_reg_target[np.where(ious_temp==1)] = box_reg


        # !!!!!!!!!!!!!!This part is for simulate the loss function with numpy and tensorflow. Don't Delate!!!!!!!!!!!!!!!
        # determine the weight, this will be implement in the tensorflow loss function in the future
        # bbox_inside_weight = np.ones(shape=(self.anchor_generator.h, self.anchor_generator.w, self.anchor_generator.n_anchors), dtype=np.float) * -1
        # print(f"[Debug INFO NP REF] Original weight in target loc: {bbox_inside_weight[np.where(anchors_target==1)]}")
        # bbox_inside_weight[np.where(anchors_target==1)] = bbox_inside_weight[np.where(anchors_target==1)] * 0 + 1
        # print(f"[Debug INFO NP REF] Modified weight in target loc: {bbox_inside_weight[np.where(anchors_target == 1)]}")
        # print(f"[Debug INFO NP REF] Number of foreground : {bbox_inside_weight[np.where(bbox_inside_weight == 1)].shape[0]}")
        # n_zeros = bbox_inside_weight[np.where(anchors_target==0)].shape[0]
        # temp_random_choice = [-1] * (n_zeros-128) + [1] * 128
        # random.shuffle(temp_random_choice)
        # # print(np.array(temp_random_choice))
        # bbox_inside_weight[np.where(anchors_target == 0)] = np.array(temp_random_choice)
        # print(f"[Debug INFO NP REF] Number of foreground + 128 random chose background : {bbox_inside_weight[np.where(bbox_inside_weight == 1)].shape[0]}")
        # bbox_outside_weight = None
        #
        # # test tensorflow
        # bbox_inside_weight = tf.ones(
        #     shape=(self.anchor_generator.h, self.anchor_generator.w, self.anchor_generator.n_anchors)) * -1
        # indices_foreground = tf.where(tf.equal(anchors_target, 1))
        # n_foreground = indices_foreground.get_shape().as_list()[0]
        # print(f"[Debug INFO TF TEST] Original weight in target loc: {tf.gather_nd(params=bbox_inside_weight, indices=indices_foreground)}")
        # bbox_inside_weight = tf.tensor_scatter_nd_update(tensor=bbox_inside_weight, indices=indices_foreground, updates=[1]*len(indices_foreground))
        # print(f"[Debug INFO TF TEST] Modified weight in target loc: {tf.gather_nd(params=bbox_inside_weight, indices=indices_foreground)}")
        # print(f"[Debug INFO TF TEST] Number of foreground : {len(indices_foreground)}")
        # indices_background = tf.where(tf.equal(anchors_target, 0))
        # print(indices_background.get_shape().as_list())
        # n_background = indices_background.get_shape().as_list()[0]
        # print(n_background)
        # selected_ratio = n_foreground/n_background
        # remain_ration = (n_background-n_foreground)/n_background
        # print(selected_ratio, remain_ration)
        # # temp_random_choice = tf.random.categorical(tf.math.log([[remain_ration, selected_ratio]]), n_background)
        # # temp_random_choice = tf.reshape(temp_random_choice, (-1,))
        # # temp_random_choice = tf.dtypes.cast(temp_random_choice, tf.float32)
        #
        # temp_random_choice = tf.random.categorical(tf.math.log([[remain_ration, selected_ratio]]), 23*40*9)
        # temp_random_choice = tf.reshape(temp_random_choice, (23,40,9))
        # temp_random_choice = tf.gather_nd(temp_random_choice, indices_background)
        # temp_random_choice = tf.dtypes.cast(temp_random_choice, tf.float32)
        # # print(np.array(temp_random_choice))
        # bbox_inside_weight = tf.tensor_scatter_nd_update(tensor=bbox_inside_weight, indices=indices_background, updates=temp_random_choice)
        # indices_train = tf.where(tf.equal(bbox_inside_weight, 1))
        #
        # print(
        #     f"[Debug INFO TF TEST] Number of foreground + {n_foreground} random chose background : {len(indices_train)}")

        return anchors_target, bbox_reg_target

    def gen_true_bbox_candidates(self, image_id, debuginfo=False):
        bboxes = self.dataset_coco.GetOriginalBboxesList(image_id=image_id)

        bboxes_ious = []    # for each gt_bbox calculate ious with candidates
        for bbox in bboxes:
            ious = bbox_tools.ious(self.anchor_generator.anchor_candidates_list, bbox)
            ious_temp = np.ones(shape=(len(ious)), dtype=np.float) * 0.5
            # other author's implementations are use -1 to indicate ignoring, here use 0.5 to use max
            ious_temp = np.where(np.asarray(ious)>0.7, 1, ious_temp)
            ious_temp = np.where(np.asarray(ious)<0.3, 0, ious_temp)
            ious_temp[np.argmax(ious)] = 1
            bboxes_ious.append(ious_temp)




        # for each gt_box, determine the box reg target
        true_bboxes = []
        for index, bbox_ious in enumerate(bboxes_ious):
            ious_temp = np.reshape(bbox_ious, newshape=(self.anchor_generator.h, self.anchor_generator.w, self.anchor_generator.n_anchors))
            candidate_boxes = self.anchor_generator.anchor_candidates[np.where(ious_temp == 1)]
            n = candidate_boxes.shape[0]
            for i in range(n):
                true_bboxes.append(candidate_boxes[i])
        return true_bboxes


    def gen_train_input(self, image_id):
        return self.dataset_coco.GetOriginalImage(image_id=image_id)

    def gen_train_data(self):
        inputs = []
        anchor_targets = []
        bbox_targets = []
        for image_id in self.dataset_coco.image_ids:
            inputs.append(self.gen_train_input(image_id))
            anchor_target, bbox_target = self.gen_train_target(image_id)
            anchor_targets.append(anchor_target)
            bbox_targets.append(bbox_target)
        return np.array(inputs), np.array(anchor_targets), np.array(bbox_targets)


    def _validate_bbox(self,image_id, bboxes):
        img1 = self.dataset_coco.GetOriginalImage(image_id=image_id)
        for bbox in bboxes:
            color = (random.randint(0, 255), random.randint(0, 255), random.randint(0, 255))
            img1 = cv.rectangle(img1, (bbox[1], bbox[0]), (bbox[3], bbox[2]), color, 4)
        plt.imshow(img1)
        plt.show()

    def _validata_masks(self, image_id):
        img1 = self.dataset_coco.GetOriginalImage(image_id=image_id)
        temp_img = np.zeros(shape=img1.shape, dtype=np.uint8)
        Masks = self.dataset_coco.GetOriginalSegmsMaskList(image_id=image_id)
        for mask in Masks:
            color = (random.randint(0, 255), random.randint(0, 255), random.randint(0, 255))
            temp_img[:, :, 0][mask.astype(bool)] = color[0]
            temp_img[:, :, 1][mask.astype(bool)] = color[1]
            temp_img[:, :, 2][mask.astype(bool)] = color[2]
        img1 = (img1 * 0.5 + temp_img * 0.5).astype(np.uint8)
        plt.imshow(img1, cmap='gray')
        plt.show()



def test2():
    BASE_PATH = '/Users/shuzhiliu/Google Drive/KyoceraRobotAI/mmdetection_tools/data'
    imagefolder_path='/Users/shuzhiliu/Google Drive/KyoceraRobotAI/mmdetection_tools/LocalData_Images'
    DATASET_ID = '1940091026744'
    image_id = '20191119T063709-cca043ed-32fe-4da0-ba75-e4a12b88eef4'
    t1 = NN_data_generator(file=f"{BASE_PATH}/{DATASET_ID}/annotations/train.json",
                           imagefolder_path=imagefolder_path)
    bboxes = t1.dataset_coco.GetOriginalBboxesList(image_id=image_id)
    t1._validate_bbox(image_id=image_id, bboxes=bboxes)
    t1._validata_masks(image_id=image_id)
    t1.gen_train_target(image_id=image_id)


def test():
    data1 = coco_tools(file=f"{BASE_PATH}/{DATASET_ID}/annotations/train.json",
                       imagefolder_path=imagefolder_path)
    img1 = data1.GetOriginalImage(image_id=image_id)
    print(data1.images)
    bboxes = data1.GetOriginalBboxesList(image_id=image_id)
    print(bboxes)
    # img1 = np.zeros(shape=(720,1280,3), dtype=np.uint8)
    for bbox in bboxes:
        color = (random.randint(0,255),random.randint(0,255),random.randint(0,255))
        # cv.rectangle(img1,(bbox[0],bbox[1]), (bbox[2],bbox[3]), 255)
        # print(bbox)
        # cv.rectangle(img=img1,rec=(bbox[1],bbox[0],bbox[3]-bbox[1],bbox[2]-bbox[0]), color=color, thickness=4)
        cv.rectangle(img1, (bbox[1],bbox[0]), (bbox[3],bbox[2]), color, 4)
    plt.imshow(img1)
    plt.show()

    g1 = gen_candidate_anchors()
    print(len(g1.anchor_candidates_list))
    ious = bbox_tools.ious(g1.anchor_candidates_list, bboxes[0])
    ious[np.argmax(ious)] = 1
    print(len(ious))
    ious_np = np.reshape(ious, newshape=(23,40,9))
    index = np.where(ious_np==1)
    print(index)

