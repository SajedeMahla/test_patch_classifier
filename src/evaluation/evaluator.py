from model_factory import ModelBuilderBase
from pathlib import Path
import shutil
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from sklearn.metrics import *
from sklearn import metrics
from prettytable import PrettyTable
import mlflow
import typing
from model_factory import PatchModel
from training import Exporter


class Evaluator:
    def __init__(self, config):
        self.config = config
        # self.history_path = self.config.info_training.history_output_path
        self.saving_path = self.config.evaluation.saving_dir
        self.random_seed = self.config.general_info.random_seed
        self.class_names = self.config.general_info.classes
        self.confusion_matrix_flag = self.config.evaluation.confusion_matrix
        self.classification_report_flag = self.config.evaluation.classification_report
        self.performance_metrics_flag = self.config.evaluation.performance_metrics
        self.precision_recall_flag = self.config.evaluation.precision_recall_curves
        self.auc_flag = self.config.evaluation.auc_curves
        self.y_truth = None
        self.predictions = None
        self.y_truth_arg = None
        self.predictions_arg = None
        self.y_pred_multi = None

    def evaluate(self,
                 model: ModelBuilderBase,
                 test_data_gen,
                 active_run: typing.Optional[mlflow.ActiveRun] = None
                 ):

        with active_run as active_run:
            run_id = active_run.info.run_id

            mlflow.log_param('base_model_name', self.config.mlflow.model_name)
            mlflow.log_param('training_mode', self.config.mlflow.training_mode)
            mlflow.log_param('image_height', self.config.general_info.image_height)
            mlflow.log_param('image_width', self.config.general_info.image_width)
            mlflow.log_param('image_channels', self.config.general_info.image_channels)
            mlflow.log_param('learning_rate', self.config.info_training.initial_learning_rate)
            mlflow.log_param('dataset_name', self.config.mlflow.dataset)

            predictions = model.predict(test_data_gen, verbose=1)
            y_truth = test_data_gen.get_y_true()
            predictions_arg = np.argmax(predictions, axis=1)

            print('predictions',predictions)
            print('len p', len(predictions))
            print('\n\n')
            print('predictions_arg' , predictions_arg )
            print('len predictions_arg,', len(predictions_arg))

            y_pred_multi = np.eye((len(self.class_names)))[predictions_arg]
            y_truth_arg = np.argmax(y_truth, axis=1)

            print('\n\n')
            print('y_truth ', y_truth )

            self.y_truth = y_truth
            self.predictions = predictions
            self.y_truth_arg = y_truth_arg
            self.predictions_arg = predictions_arg
            self.y_pred_multi = y_pred_multi

            if self.confusion_matrix_flag:
                self.print_confusion_matrix()

            if self.performance_metrics_flag:
                self.print_performance_metrics(self.y_truth_arg, self.predictions_arg)

            if self.classification_report_flag:
                cr = self.classification_report()
                print(cr)

            if self.precision_recall_flag:
                self.print_precision_recall_curves()

            if self.auc_flag:
                self.print_auc_curves()

            df = pd.read_csv(self.config.evaluation.eval_saving_path)
            metric_names = df.columns[2:]
            metrics_dict = {}
            for i in range(len(self.class_names)):
                clss_df = df.loc[df['Class Names'] == self.class_names[i]]
                for j in range(len(metric_names)):
                    metrics_dict[self.class_names[i] + '_' + metric_names[j]] = clss_df[metric_names[j]].values[0]
            mlflow.log_metrics(metrics_dict)

        # pyfuncmodel = PatchModel()
        # exporter = Exporter(self.config, self.run_dir)
        # exporter.log_model_to_mlflow(active_run,
        #                              pyfuncmodel,
        #                              Path('../config.yaml')
        #                              )

    def calc_confusion_matrix(self):
        matrix = confusion_matrix(self.y_truth_arg, self.predictions_arg)
        cm = matrix.astype('float') / matrix.sum(axis=1)[:, np.newaxis]
        return cm

    def print_confusion_matrix(self):
        cm = self.calc_confusion_matrix()
        plt.figure(figsize=(12, 8))
        sns.heatmap(cm, cmap='crest', linecolor='white', linewidths=1, annot=True, xticklabels=self.class_names,
                    yticklabels=self.class_names)
        plt.title('Confusion Matrix')
        plt.ylabel('True Label')
        plt.xlabel('Predicted Label')
        plt.savefig(self.saving_path + "/print_confusion_matrix.png")

    def calc_rates(self, i):
        y_class_pred = self.y_pred_multi[:, i]
        y_class_true = self.y_truth[:, i]
        conf = confusion_matrix(y_class_true, y_class_pred)
        cm = conf
        tn, fp, fn, tp = cm.ravel()
        return tn, fp, fn, tp

    def calc_classification_report(self, i):
        tn, fp, fn, tp = self.calc_rates(i)
        sensitivity_recall = np.round(tp / (tp + fn), 4)
        Specifity = np.round(tn / (tn + fp), 4)
        PPV_precision = np.round(tp / (tp + fp), 4)
        NPV = np.round(tn / (tn + fn), 4)
        prevalence = np.round((tp + fn) / (tn + fp + fn + tp), 4)
        acc_sp = np.round((tp + tn) / (tn + fp + fn + tp), 4)
        f1_score = np.round((2 * tp) / ((2 * tp) + fp + fn), 4)
        support = np.count_nonzero(self.y_truth[:, i])
        return sensitivity_recall, Specifity, PPV_precision, NPV, prevalence, acc_sp, f1_score, support

    def classification_report(self):

        acc = np.round(accuracy_score(self.y_truth_arg, self.predictions_arg), 4)
        print('Total Accuracy:', acc)
        columns = ['label', 'Class Names', 'Sensitivity', 'Specificity',
                   'PPV', 'NPV', 'Prevalence', 'Accuracy', 'F1_Score', 'Support']
        myTable = PrettyTable(columns)

        all_metrics = []
        for i in range(len(self.class_names)):
            sensitivity_recall, Specifity, PPV_precision, NPV, prevalence, acc_sp, f1_score, support = self.calc_classification_report(
                i)
            metrics_list = []
            label = i
            class_name = self.class_names[i]

            metrics_list.append([label, class_name, sensitivity_recall,
                                 Specifity, PPV_precision, NPV, prevalence, acc_sp, f1_score, support])
            all_metrics.append([label, class_name, sensitivity_recall,
                                Specifity, PPV_precision, NPV, prevalence, acc_sp, f1_score, support])
            myTable.add_row(metrics_list[-1])
        metrics_df = pd.DataFrame(all_metrics, columns=columns)
        metrics_df.to_csv(self.config.evaluation.eval_saving_path, index=False)
        # print(metrics_df)

        metrics_values = metrics_df.iloc[:, 2:].values
        total_support = self.y_truth_arg.shape[0]
        print(total_support)

        # Macro Average
        filtered_mv = metrics_values[metrics_values[:, -1] != 0]
        macro_avg = np.mean(filtered_mv[:, :-1], axis=0)
        macro_avg = np.round(macro_avg, 4)

        # Weighted Average
        weighted_avg = list(map(lambda x: (x[:-1] * x[-1]), filtered_mv))
        weighted_avg = np.array(weighted_avg) / total_support
        weighted_avg = np.sum(weighted_avg, axis=0)
        weighted_avg = np.round(weighted_avg, 4)

        avgs_df = pd.DataFrame((macro_avg, weighted_avg),
                               columns=columns[2:-1])
        avgs_df['Support'] = total_support

        method_names = ['Macro Avg', 'Weighted Avg']

        myTable.add_row(['---'] * len(columns))
        for i, each_method in enumerate(method_names):
            if each_method == 'Weighted Avg':
                continue
            myTable.add_row(np.concatenate([['---', each_method], avgs_df.iloc[i].values]))

        return myTable

    def print_performance_metrics(self, y_test, y_pred):
        print('Accuracy:', np.round(metrics.accuracy_score(y_test, y_pred), 4))
        print('Precision:', np.round(metrics.precision_score(y_test, y_pred, average='weighted'), 4))
        print('Recall:', np.round(metrics.recall_score(y_test, y_pred, average='weighted'), 4))
        print('F1 Score:', np.round(metrics.f1_score(y_test, y_pred, average='weighted'), 4))
        print('Cohen Kappa Score:', np.round(metrics.cohen_kappa_score(y_test, y_pred), 4))
        print('Matthews Corrcoef:', np.round(metrics.matthews_corrcoef(y_test, y_pred), 4))
        if len(np.unique(y_test)) == 2:
            print('ROC AUC:', metrics.roc_auc_score(y_test, y_pred))
        print('\t\tClassification Report:\n',
              metrics.classification_report(y_test, y_pred,
                                            labels=list(np.arange(len(self.class_names))),
                                            target_names=self.class_names))

    def print_precision_recall_curves(self):
        y_true = self.y_truth
        y_hat = self.predictions
        class_names = self.class_names
        save_name = 'PR_Curve'
        # For each class
        precision = dict()
        recall = dict()
        average_precision = dict()
        for i in range(len(class_names)):
            precision[i], recall[i], _ = precision_recall_curve(y_true[:, i],
                                                                y_hat[:, i])
            average_precision[i] = average_precision_score(y_true[:, i], y_hat[:, i])

        # A "micro-average": quantifying score on all classes jointly
        precision["micro"], recall["micro"], _ = precision_recall_curve(y_true.ravel(),
                                                                        y_hat.ravel())
        average_precision["micro"] = average_precision_score(y_true, y_hat,
                                                             average="micro")
        plt.figure(figsize=(10, 5))
        for i in range(len(class_names)):
            plt.plot(recall[i], precision[i],
                     label='Precision-recall for class {0} (area = {1:0.2f})'.format(class_names[i],
                                                                                     average_precision[i]))
        plt.xlim([0.0, 1.0])
        plt.ylim([0.0, 1.05])
        plt.xlabel('Recall')
        plt.ylabel('Precision')
        plt.title('Precision-Recall Curve')
        plt.legend(loc="lower left")
        plt.savefig(self.saving_path + '/' + save_name + '.png')

    def print_auc_curves(self):
        y_true = self.y_truth
        y_hat = self.predictions
        class_names = self.class_names
        save_name = 'ROC_Curve'
        fpr = dict()
        tpr = dict()
        roc_auc = dict()
        roc_auc_sc = dict()
        for i in range(len(class_names)):
            fpr[i], tpr[i], _ = roc_curve(y_true[:, i], y_hat[:, i])
            roc_auc[i] = auc(fpr[i], tpr[i])
            roc_auc_sc[i] = roc_auc_score(y_true[:, i], y_hat[:, i])

        # Compute micro-average ROC curve and ROC area
        fpr["micro"], tpr["micro"], _ = roc_curve(y_true.ravel(), y_hat.ravel())
        roc_auc["micro"] = auc(fpr["micro"], tpr["micro"])
        plt.figure(figsize=(10, 5))
        for i in range(len(class_names)):
            plt.plot(fpr[i], tpr[i], label='ROC curve for class {} (area = %0.2f)'.format(class_names[i]) % roc_auc[i])
        plt.plot([0, 1], [0, 1], 'k--')
        plt.xlim([0.0, 1.0])
        plt.ylim([0.0, 1.05])
        plt.xlabel('False Positive Rate')
        plt.ylabel('True Positive Rate')
        plt.title('Receiver Operating Characteristic Curve')
        plt.legend(loc="lower right")
        plt.savefig(self.saving_path + '/' + save_name + '.png')
