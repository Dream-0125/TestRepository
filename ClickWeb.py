# _*_coding:utf-8 _*_
# !/usr/bin/python3
import datetime
import random
import time
from datetime import date
from email.mime.text import MIMEText
from email.utils import formataddr

# Reference:********************************
# encoding: utf-8
# @Time: 2024/9/23 11:30
# @Author: v.xiongmx
# @File: exercise.py
# @Function:
# @Method:
# Reference:********************************
import holidays
import undetected_chromedriver as uc
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
import os
import smtplib


def is_holidays():
	"""
	判断是否是节假日
	"""
	holiday = holidays.country_holidays('CN')
	now_date = str(date.today()).split('-')
	special_date = date(int(now_date[0]), int(now_date[1]), int(now_date[2]))
	if special_date in holiday:
		return True
	else:
		return False


def click_time():
	"""
	打卡时间
	"""
	return datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')


def waiting_time():
	"""
	等待时间
	"""
	time.sleep(random.randint(400, 1500))


def click_sign():
	"""
	打卡
	"""
	chrome_options = Options()
	s = Service(r"chromedriver.exe")
	driver = uc.Chrome(service=s, options=chrome_options)
	driver.get('https://hr.yoozoo.com/self-service/personal-attendance')
	driver.find_element(By.ID, 'username').send_keys('v.xiongmx')
	time.sleep(3)
	driver.find_element(By.ID, 'password').send_keys('Xiongmx123')
	time.sleep(3)
	driver.find_element(By.NAME, 'submit').click()
	time.sleep(4)
	driver.find_element(By.ID, 'sigin').click()


def send_message():
	try:
		# 设置邮件内容
		# 邮箱配置
		EMAIL_ADDRESS = '3330308930@qq.com'  # 替换为你的 QQ 邮箱地址
		EMAIL_PASSWORD = 'wfnwvhuletpodaab'  # 替换为你的授权码
		msg = MIMEText(f'打卡成功!打卡时间{click_time()}', 'plain', 'utf-8')
		msg['From'] = formataddr(('熊梦想', EMAIL_ADDRESS))  # 显示发件人名称和地址
		msg['To'] = '3330308930@qq.com'  # 收件人地址
		msg['Subject'] = '打卡结果'  # 邮件主题

		# 连接 SMTP 服务器
		with smtplib.SMTP_SSL('smtp.qq.com', 465) as smtp:
			smtp.login(EMAIL_ADDRESS, EMAIL_PASSWORD)  # 登录 QQ 邮箱
			smtp.sendmail(EMAIL_ADDRESS, ['3330308930@qq.com'], msg.as_string())  # 发送邮件
			print('邮件发送成功！')
	except smtplib.SMTPException as e:
		print(f'邮件发送失败: {e}')


if __name__ == '__main__':
	if not is_holidays():
		waiting_time()
		click_sign()
	send_message()
