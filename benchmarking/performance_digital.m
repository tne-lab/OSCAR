%% Initialize DAQ
duration = 30;
per = 1/50;
fs=250000;
dq = daq("ni");
addinput(dq, "Dev2", "ai0", "Voltage");
addinput(dq, "Dev2", "ai1", "Voltage");
addoutput(dq, "Dev2", "ao0", "Voltage");
dq.Rate = fs;
outData = zeros(duration*fs,1);
outData(mod(1:length(outData),fs*per)<fs*per/2)=3.3;
outData=[zeros(fs,1); outData; zeros(fs,1)];
%% Start recording
inData = readwrite(dq,outData,"OutputFormat","Matrix");
%%
outData = inData(:,2);
figure
plot((1:100:length(outData))/fs,outData(1:100:end))
hold on
plot((1:100:length(outData))/fs,inData(1:100:end,1))
temp=find(diff(outData>2.5)~=0);
temp2=find(diff(inData(:,1)>2.5)~=0);
temp3=temp(1:end-2)-temp2(1:end);
lat=-temp3/fs*1000;
figure
hold on
histogram(lat)