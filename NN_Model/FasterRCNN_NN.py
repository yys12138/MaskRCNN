from NN_Components import Backbone, RPN, RoI
import numpy as np
from NN_Helper import NN_data_generator, bbox_tools, bbox_tools_tf
import tensorflow as tf
from Debugger import DebugPrint
from Configs.FasterRCNN_config import Param
import os
import random

os.environ['KMP_DUPLICATE_LIB_OK'] = 'True'  # for mac os tensorflow setting


# tf.keras.backend.set_floatx('float64')

class FasterRCNN():
    def __init__(self):
        b1 = Backbone(IMG_SHAPE=Param.IMG_RESIZED_SHAPE, n_stage=Param.N_STAGE)
        self.IMG_SHAPE = Param.IMG_RESIZED_SHAPE
        self.backbone_model = b1.backbone_model
        # self.backbone_model.trainable= False
        # === RPN part ===
        self.RPN = RPN(backbone_model=self.backbone_model,
                       lambda_factor=Param.LAMBDA_FACTOR,
                       batch=Param.BATCH_RPN,
                       lr=Param.LR)
        self.RPN_model = self.RPN.RPN_with_backbone_model

        # === RoI part ===
        self.RoI = RoI(backbone_model=self.backbone_model,
                       IMG_SHAPE=self.IMG_SHAPE,
                       n_output_classes=Param.N_OUT_CLASS,
                       lr=Param.LR)
        self.RoI_with_backbone_model = self.RoI.RoI_with_backbone_model
        self.RoI_header = self.RoI.RoI_header_model

        # === Data part ===
        self.train_data_generator = NN_data_generator(
            file=Param.DATA_JSON_FILE,
            imagefolder_path=Param.PATH_IMAGES,
            base_size=Param.BASE_SIZE,
            ratios=Param.RATIOS,
            scales=Param.SCALES,
            n_anchors=Param.N_ANCHORS,
            img_shape_resize=Param.IMG_RESIZED_SHAPE,
            n_stage=Param.N_STAGE,
            threshold_iou_rpn=Param.THRESHOLD_IOU_RPN,
            threshold_iou_roi=Param.THRESHOLD_IOU_RoI)
        self.cocotool = self.train_data_generator.dataset_coco

        self.anchor_candidate_generator = self.train_data_generator.gen_candidate_anchors
        self.anchor_candidates = self.anchor_candidate_generator.anchor_candidates

    def test_loss_function(self):
        inputs, anchor_targets, bbox_targets = self.train_data_generator.gen_train_data_RPN_all()
        print(inputs.shape, anchor_targets.shape, bbox_targets.shape)
        input1 = np.reshape(inputs[0, :, :, :], (1, 720, 1280, 3))
        anchor1 = np.reshape(anchor_targets[0, :, :, :], (1, 23, 40, 9))
        anchor2 = tf.convert_to_tensor(anchor1)
        anchor2 = tf.dtypes.cast(anchor2, tf.int32)
        anchor2 = tf.one_hot(anchor2, 2, axis=-1)
        print(anchor1)
        bbox1 = np.reshape(bbox_targets[0, :, :, :, :], (1, 23, 40, 9, 4))
        loss = self.RPN._RPN_loss(anchor1, bbox1, anchor2, bbox1)
        print(loss)

    def _proposal_boxes(self, RPN_Anchor_Pred, RPN_BBOX_Regression_Pred, anchor_candidates):
        # === Selection part ===
        # top_values, top_indices = tf.math.top_k()
        RPN_Anchor_Pred = tf.slice(RPN_Anchor_Pred, [0, 0, 0, 0, 1], [1,
                                                                      self.anchor_candidate_generator.h,
                                                                      self.anchor_candidate_generator.w,
                                                                      self.anchor_candidate_generator.n_anchors,
                                                                      1])  # second channel is foreground
        # squeeze the pred of anchor and bbox_reg
        RPN_Anchor_Pred = tf.squeeze(RPN_Anchor_Pred)
        RPN_BBOX_Regression_Pred = tf.squeeze(RPN_BBOX_Regression_Pred)
        shape1 = tf.shape(RPN_Anchor_Pred)
        # flatten the pred of anchor to get top N values and indices
        RPN_Anchor_Pred = tf.reshape(RPN_Anchor_Pred, (-1,))
        n_anchor_proposal = Param.ANCHOR_PROPOSAL_N
        top_values, top_indices = tf.math.top_k(RPN_Anchor_Pred,
                                                n_anchor_proposal)  # top_k has sort function. it's important here
        top_indices = tf.gather_nd(top_indices, tf.where(tf.greater(top_values, Param.ANCHOR_THRESHOLD)))
        top_values = tf.gather_nd(top_values, tf.where(tf.greater(top_values, Param.ANCHOR_THRESHOLD)))

        top_indices = tf.reshape(top_indices, (-1, 1))
        update_value = tf.math.add(top_values, 1)
        RPN_Anchor_Pred = tf.tensor_scatter_nd_update(RPN_Anchor_Pred, top_indices, update_value)
        RPN_Anchor_Pred = tf.reshape(RPN_Anchor_Pred, shape1)

        # --- find the base boxes ---
        Anchor_Pred_top_indices = tf.where(tf.greater(RPN_Anchor_Pred, 1))
        base_boxes = tf.gather_nd(anchor_candidates, Anchor_Pred_top_indices)

        # --- find the bbox_regs ---
        # flatten the bbox_reg by last dim to use top_indices to get final_box_reg
        RPN_BBOX_Regression_Pred_shape = tf.shape(RPN_BBOX_Regression_Pred)
        RPN_BBOX_Regression_Pred = tf.reshape(RPN_BBOX_Regression_Pred, (-1, RPN_BBOX_Regression_Pred_shape[-1]))
        final_box_reg = tf.gather_nd(RPN_BBOX_Regression_Pred, top_indices)

        # Convert to numpy to plot
        final_box = bbox_tools_tf.bbox_reg2truebox(base_boxes=base_boxes, regs=final_box_reg)
        return np.array(final_box).astype(np.float)
        # return final_box

    def FasterRCNN_output(self):
        image_ids = self.train_data_generator.dataset_coco.image_ids
        inputs, anchor_targets, bbox_reg_targets = self.train_data_generator.gen_train_data_RPN_one(image_ids[0])
        print(inputs.shape, anchor_targets.shape, bbox_reg_targets.shape)
        image = np.reshape(inputs[0, :, :, :], (1, self.IMG_SHAPE[0], self.IMG_SHAPE[1], 3))
        RPN_Anchor_Pred, RPN_BBOX_Regression_Pred = self.RPN_model(image)
        proposed_boxes = self._proposal_boxes(RPN_Anchor_Pred, RPN_BBOX_Regression_Pred,
                                              self.anchor_candidates)
        pred_class, pred_box_reg = self.RoI_with_backbone_model([image, proposed_boxes])
        print(pred_class, pred_box_reg)
        print(proposed_boxes)
        print(np.max(proposed_boxes), np.max(pred_box_reg))
        final_box = bbox_tools.bbox_reg2truebox(base_boxes=proposed_boxes, regs=pred_box_reg)
        final_box = bbox_tools.clip_boxes(final_box, self.IMG_SHAPE)
        # get top k element
        # k = 300
        # pred_class_value = np.max(pred_class, axis=1)
        # indices_top = np.argpartition(a=pred_class_value, kth=-k)[-k:]
        # final_box = final_box[indices_top]
        self.cocotool.DrawBboxes(Original_Image=image[0], Bboxes=final_box.tolist(), show=True, savefile=True,
                                 path=Param.PATH_DEBUG_IMG, savename='6PredRoISBoxes')

        # === Non maximum suppression ===
        final_box_temp = np.array(final_box).astype(np.int)
        nms_boxes_list = []
        while final_box_temp.shape[0] > 0:
            ious = self.nms_loop_np(final_box_temp)
            nms_boxes_list.append(
                final_box_temp[0, :])  # since it's sorted by the value, here we can pick the first one each time.
            final_box_temp = final_box_temp[ious < Param.RPN_NMS_THRESHOLD]
        DebugPrint('number of box after nms', len(nms_boxes_list))
        self.cocotool.DrawBboxes(Original_Image=image[0], Bboxes=nms_boxes_list, show=True, savefile=True,
                                 path=Param.PATH_DEBUG_IMG, savename='7PredRoINMSBoxes')

    def test_proposal_visualization(self):
        # === Prediction part ===
        image_ids = self.train_data_generator.dataset_coco.image_ids
        inputs, anchor_targets, bbox_reg_targets = self.train_data_generator.gen_train_data_RPN_one(image_ids[0])
        print(inputs.shape, anchor_targets.shape, bbox_reg_targets.shape)
        input1 = np.reshape(inputs[0, :, :, :], (1, self.IMG_SHAPE[0], self.IMG_SHAPE[1], 3))
        RPN_Anchor_Pred, RPN_BBOX_Regression_Pred = self.RPN_model.predict(input1, batch_size=1)
        print(RPN_Anchor_Pred.shape, RPN_BBOX_Regression_Pred.shape)

        # === Selection part ===
        # top_values, top_indices = tf.math.top_k()
        RPN_Anchor_Pred = tf.slice(RPN_Anchor_Pred, [0, 0, 0, 0, 1],
                                   [1, self.anchor_candidate_generator.h, self.anchor_candidate_generator.w,
                                    self.anchor_candidate_generator.n_anchors, 1])  # second channel is foreground
        print(RPN_Anchor_Pred.shape, RPN_BBOX_Regression_Pred.shape)
        # squeeze the pred of anchor and bbox_reg
        RPN_Anchor_Pred = tf.squeeze(RPN_Anchor_Pred)
        RPN_BBOX_Regression_Pred = tf.squeeze(RPN_BBOX_Regression_Pred)
        shape1 = tf.shape(RPN_Anchor_Pred)
        print(RPN_Anchor_Pred.shape, RPN_BBOX_Regression_Pred.shape)
        # flatten the pred of anchor to get top N values and indices
        RPN_Anchor_Pred = tf.reshape(RPN_Anchor_Pred, (-1,))
        n_anchor_proposal = Param.ANCHOR_PROPOSAL_N
        top_values, top_indices = tf.math.top_k(RPN_Anchor_Pred,
                                                n_anchor_proposal)  # top_k has sort function. it's important here
        top_indices = tf.gather_nd(top_indices, tf.where(tf.greater(top_values, Param.ANCHOR_THRESHOLD)))
        top_values = tf.gather_nd(top_values, tf.where(tf.greater(top_values, Param.ANCHOR_THRESHOLD)))

        DebugPrint('top values', top_values)

        # test_indices = tf.where(tf.greater(tf.reshape(RPN_Anchor_Pred, (-1,)), 0.9))
        # print(test_indices)

        top_indices = tf.reshape(top_indices, (-1, 1))
        DebugPrint('top indices', top_indices)
        update_value = tf.math.add(top_values, 1)
        RPN_Anchor_Pred = tf.tensor_scatter_nd_update(RPN_Anchor_Pred, top_indices, update_value)
        RPN_Anchor_Pred = tf.reshape(RPN_Anchor_Pred, shape1)

        # --- find the base boxes ---
        Anchor_Pred_top_indices = tf.where(tf.greater(RPN_Anchor_Pred, 1))
        DebugPrint('original_indices shape', Anchor_Pred_top_indices.shape)
        DebugPrint('original_indices', Anchor_Pred_top_indices)
        base_boxes = tf.gather_nd(self.anchor_candidates, Anchor_Pred_top_indices)
        DebugPrint('base_boxes shape', base_boxes.shape)
        DebugPrint('base_boxes', base_boxes)
        base_boxes = np.array(base_boxes)

        # --- find the bbox_regs ---
        # flatten the bbox_reg by last dim to use top_indices to get final_box_reg
        RPN_BBOX_Regression_Pred_shape = tf.shape(RPN_BBOX_Regression_Pred)
        RPN_BBOX_Regression_Pred = tf.reshape(RPN_BBOX_Regression_Pred, (-1, RPN_BBOX_Regression_Pred_shape[-1]))
        DebugPrint('RPN_BBOX_Regression_Pred shape', RPN_BBOX_Regression_Pred.shape)
        final_box_reg = tf.gather_nd(RPN_BBOX_Regression_Pred, top_indices)
        DebugPrint('final box reg values', final_box_reg)

        # Convert to numpy to plot
        final_box_reg = np.array(final_box_reg)
        DebugPrint('final box reg shape', final_box_reg.shape)
        DebugPrint('max value of final box reg', np.max(final_box_reg))
        final_box = bbox_tools.bbox_reg2truebox(base_boxes=base_boxes, regs=final_box_reg)

        # === Non maximum suppression ===
        final_box_temp = np.array(final_box).astype(np.int)
        nms_boxes_list = []
        while final_box_temp.shape[0] > 0:
            ious = self.nms_loop_np(final_box_temp)
            nms_boxes_list.append(
                final_box_temp[0, :])  # since it's sorted by the value, here we can pick the first one each time.
            final_box_temp = final_box_temp[ious < Param.RPN_NMS_THRESHOLD]
        DebugPrint('number of box after nms', len(nms_boxes_list))

        # Need to convert above instructions to tf operations

        # === visualization part ===
        # clip the boxes to make sure they are legal boxes
        DebugPrint('max value of final box', np.max(final_box))
        final_box = bbox_tools.clip_boxes(final_box, self.IMG_SHAPE)

        original_boxes = self.cocotool.GetOriginalBboxesList(image_id=self.cocotool.image_ids[0])
        self.cocotool.DrawBboxes(Original_Image=input1[0], Bboxes=original_boxes, show=True, savefile=True,
                                 path=Param.PATH_DEBUG_IMG, savename='1GroundTruthBoxes')
        target_anchor_boxes, target_classes = self.train_data_generator.gen_target_anchor_bboxes_classes_for_Debug(
            image_id=self.cocotool.image_ids[0])
        self.cocotool.DrawBboxes(Original_Image=input1[0], Bboxes=target_anchor_boxes, show=True, savefile=True,
                                 path=Param.PATH_DEBUG_IMG, savename='2TrueAnchorBoxes')
        self.cocotool.DrawBboxes(Original_Image=input1[0], Bboxes=base_boxes.tolist(), show=True, savefile=True,
                                 path=Param.PATH_DEBUG_IMG, savename='3PredAnchorBoxes')
        self.cocotool.DrawBboxes(Original_Image=input1[0], Bboxes=final_box.tolist(), show=True, savefile=True,
                                 path=Param.PATH_DEBUG_IMG, savename='4PredRegBoxes')
        self.cocotool.DrawBboxes(Original_Image=input1[0], Bboxes=nms_boxes_list, show=True, savefile=True,
                                 path=Param.PATH_DEBUG_IMG, savename='5PredNMSBoxes')

    def test_total_visualization(self):
        # === prediction part ===
        input_images, target_anchor_bboxes, target_classes = self.train_data_generator.gen_train_data_RoI_one(
            self.train_data_generator.dataset_coco.image_ids[0],
            self.train_data_generator.gen_candidate_anchors.anchor_candidates_list)
        input_images, target_anchor_bboxes, target_classes = np.asarray(input_images).astype(np.float), np.asarray(
            target_anchor_bboxes), np.asarray(target_classes)
        # TODO:check tf.image.crop_and_resize
        input_images2 = input_images[:1].astype(np.float)
        print(input_images2.shape)
        target_anchor_bboxes2 = target_anchor_bboxes[:1].astype(np.float)
        print(target_anchor_bboxes2.shape)
        class_header, box_reg_header = self.RoI_with_backbone_model.predict([input_images2, target_anchor_bboxes2])
        print(class_header.shape, box_reg_header.shape)
        print(class_header)

    def nms_loop_np(self, boxes):
        # boxes : (N, 4), box_1target : (4,)
        # box axis format: (x1,y1,x2,y2)
        # boxes = boxes.astype(np.float)
        box_1target = np.ones(shape=boxes.shape)
        zeros = np.zeros(shape=boxes.shape)
        box_1target = box_1target * boxes[0, :]
        boxBArea = (box_1target[:, 2] - box_1target[:, 0] + 1) * (box_1target[:, 3] - box_1target[:, 1] + 1)
        # determine the (x, y)-coordinates of the intersection rectangle
        xA = np.max(np.array([boxes[:, 0], box_1target[:, 0]]), axis=0)
        yA = np.max(np.array([boxes[:, 1], box_1target[:, 1]]), axis=0)
        xB = np.min(np.array([boxes[:, 2], box_1target[:, 2]]), axis=0)
        yB = np.min(np.array([boxes[:, 3], box_1target[:, 3]]), axis=0)

        # compute the area of intersection rectangle
        interArea = np.max(np.array([zeros[:, 0], xB - xA + 1]), axis=0) * np.max(np.array([zeros[:, 0], yB - yA + 1]),
                                                                                  axis=0)

        # compute the area of both the prediction and ground-truth
        # rectangles
        boxAArea = (boxes[:, 2] - boxes[:, 0] + 1) * (boxes[:, 3] - boxes[:, 1] + 1)

        # compute the intersection over union by taking the intersection
        # area and dividing it by the sum of prediction + ground-truth
        # areas - the interesection area
        ious = (interArea / (boxAArea + boxBArea - interArea))

        # return the intersection over union value
        return ious

    def nms_loop_tf(self, boxes):
        ious = tf.numpy_function(func=self.nms_loop_np, inp=[boxes], Tout=tf.float32)

    def train_RPN_RoI(self, ):
        # TODO: use the output of RPN to train RoI
        image_ids = self.train_data_generator.dataset_coco.image_ids
        for epoch in range(Param.EPOCH):
            print(f'epoch : {epoch}')
            temp_image_ids = random.choices(population=image_ids, weights=None, k=8)
            # --- train RPN header first ---
            for image_id in temp_image_ids:
                inputs, anchor_targets, bbox_reg_targets = self.train_data_generator.gen_train_data_RPN_one(image_id)
                self.RPN.train_step_header(inputs, anchor_targets, bbox_reg_targets)
            for image_id in image_ids:
                # print(f'{i} th image')
                # --- train RPN with backbone---
                inputs, anchor_targets, bbox_reg_targets = self.train_data_generator.gen_train_data_RPN_one(image_id)
                self.RPN.train_step_with_backbone(inputs, anchor_targets, bbox_reg_targets)
                # --- train RoI ---
                input_img, input_box_filtered_by_iou, target_class, target_bbox_reg = self.train_data_generator.gen_train_data_RoI_one(
                    image_id, self.train_data_generator.gen_candidate_anchors.anchor_candidates_list)
                n_box = input_img.shape[0]
                # --- train RoI header first ---
                for j in range(n_box):
                    self.RoI.train_step_header(input_img[0:1], input_box_filtered_by_iou[j:j + 1],
                                               target_class[j:j + 1], target_bbox_reg[j:j + 1])
                # --- train RoI with backbone once, balance with the RPN train ---
                j = random.randint(a=0,
                                   b=n_box - 1)  # model with backbone only be trained once to balance RPN and RoI training
                self.RoI.train_step_with_backbone(input_img[j:j + 1], input_box_filtered_by_iou[j:j + 1],
                                                  target_class[j:j + 1], target_bbox_reg[j:j + 1])

                # --- train RoI with RPN proposed boxes ---
                if epoch > 10:
                    RPN_Anchor_Pred, RPN_BBOX_Regression_Pred = self.RPN_model(input_img[:1])
                    proposed_boxes = self._proposal_boxes(RPN_Anchor_Pred, RPN_BBOX_Regression_Pred,
                                                          self.anchor_candidates)
                    if len(list(proposed_boxes.tolist())) == 0:
                        continue
                    input_img, input_box_filtered_by_iou, target_class, target_bbox_reg = self.train_data_generator.gen_train_data_RoI_one(
                        image_id, proposed_boxes.tolist())
                    for j in range(n_box):
                        self.RoI.train_step_header(input_img[j:j + 1], input_box_filtered_by_iou[j:j + 1],
                                                   target_class[j:j + 1], target_bbox_reg[j:j + 1])

    def save_weight(self):
        self.RPN_model.save_weights(filepath=f"{Param.PATH_MODEL}/RPN_model")
        self.RoI_header.save_weights(filepath=f"{Param.PATH_MODEL}/RoI_header_model")
        self.backbone_model.save_weights(filepath=f"{Param.PATH_MODEL}/backbone_model")

    def load_weight(self):
        self.RPN_model.load_weights(filepath=f"{Param.PATH_MODEL}/RPN_model")
        self.RoI_header.load_weights(filepath=f"{Param.PATH_MODEL}/RoI_header_model")
        self.backbone_model.load_weights(filepath=f"{Param.PATH_MODEL}/backbone_model")


if __name__ == '__main__':
    f1 = FasterRCNN()

    # f1.train_RPN_RoI()
    # f1.save_weight()
    f1.load_weight()
    f1.test_proposal_visualization()
    f1.FasterRCNN_output()
