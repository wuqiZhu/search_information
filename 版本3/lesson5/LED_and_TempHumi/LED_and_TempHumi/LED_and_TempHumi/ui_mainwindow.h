/********************************************************************************
** Form generated from reading UI file 'mainwindow.ui'
**
** Created by: Qt User Interface Compiler version 5.12.8
**
** WARNING! All changes made in this file will be lost when recompiling UI file!
********************************************************************************/

#ifndef UI_MAINWINDOW_H
#define UI_MAINWINDOW_H

#include <QtCore/QVariant>
#include <QtWidgets/QApplication>
#include <QtWidgets/QLabel>
#include <QtWidgets/QMainWindow>
#include <QtWidgets/QMenuBar>
#include <QtWidgets/QPushButton>
#include <QtWidgets/QStatusBar>
#include <QtWidgets/QWidget>

QT_BEGIN_NAMESPACE

class Ui_MainWindow
{
public:
    QWidget *centralwidget;
    QPushButton *pushButton;
    QLabel *label;
    QLabel *label_2;
    QLabel *label_pir;
    QLabel *label_light;
    QPushButton *pushButton_relay;
    QLabel *label_smoke;
    QPushButton *pushButton_relay2;
    QMenuBar *menubar;
    QStatusBar *statusbar;

    void setupUi(QMainWindow *MainWindow)
    {
        if (MainWindow->objectName().isEmpty())
            MainWindow->setObjectName(QString::fromUtf8("MainWindow"));
        MainWindow->resize(1215, 868);
        centralwidget = new QWidget(MainWindow);
        centralwidget->setObjectName(QString::fromUtf8("centralwidget"));
        pushButton = new QPushButton(centralwidget);
        pushButton->setObjectName(QString::fromUtf8("pushButton"));
        pushButton->setGeometry(QRect(180, 140, 141, 91));
        label = new QLabel(centralwidget);
        label->setObjectName(QString::fromUtf8("label"));
        label->setGeometry(QRect(430, 120, 141, 101));
        label_2 = new QLabel(centralwidget);
        label_2->setObjectName(QString::fromUtf8("label_2"));
        label_2->setGeometry(QRect(410, 290, 131, 91));
        label_pir = new QLabel(centralwidget);
        label_pir->setObjectName(QString::fromUtf8("label_pir"));
        label_pir->setGeometry(QRect(660, 120, 161, 101));
        label_light = new QLabel(centralwidget);
        label_light->setObjectName(QString::fromUtf8("label_light"));
        label_light->setGeometry(QRect(670, 270, 121, 121));
        pushButton_relay = new QPushButton(centralwidget);
        pushButton_relay->setObjectName(QString::fromUtf8("pushButton_relay"));
        pushButton_relay->setGeometry(QRect(190, 290, 131, 81));
        label_smoke = new QLabel(centralwidget);
        label_smoke->setObjectName(QString::fromUtf8("label_smoke"));
        label_smoke->setGeometry(QRect(670, 420, 161, 51));
        pushButton_relay2 = new QPushButton(centralwidget);
        pushButton_relay2->setObjectName(QString::fromUtf8("pushButton_relay2"));
        pushButton_relay2->setGeometry(QRect(190, 530, 121, 61));
        MainWindow->setCentralWidget(centralwidget);
        menubar = new QMenuBar(MainWindow);
        menubar->setObjectName(QString::fromUtf8("menubar"));
        menubar->setGeometry(QRect(0, 0, 1215, 22));
        MainWindow->setMenuBar(menubar);
        statusbar = new QStatusBar(MainWindow);
        statusbar->setObjectName(QString::fromUtf8("statusbar"));
        MainWindow->setStatusBar(statusbar);

        retranslateUi(MainWindow);

        QMetaObject::connectSlotsByName(MainWindow);
    } // setupUi

    void retranslateUi(QMainWindow *MainWindow)
    {
        MainWindow->setWindowTitle(QApplication::translate("MainWindow", "MainWindow", nullptr));
        pushButton->setText(QApplication::translate("MainWindow", "LED", nullptr));
        label->setText(QApplication::translate("MainWindow", "humi", nullptr));
        label_2->setText(QApplication::translate("MainWindow", "temp", nullptr));
        label_pir->setText(QApplication::translate("MainWindow", "pir", nullptr));
        label_light->setText(QApplication::translate("MainWindow", "light", nullptr));
        pushButton_relay->setText(QApplication::translate("MainWindow", "Fan", nullptr));
        label_smoke->setText(QApplication::translate("MainWindow", "Smoke: --", nullptr));
        pushButton_relay2->setText(QApplication::translate("MainWindow", "LED Lamp", nullptr));
    } // retranslateUi

};

namespace Ui {
    class MainWindow: public Ui_MainWindow {};
} // namespace Ui

QT_END_NAMESPACE

#endif // UI_MAINWINDOW_H
