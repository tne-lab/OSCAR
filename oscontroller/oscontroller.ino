#include "DAC8554.h"
#include <digitalWriteFast.h>

#define cbi(sfr, bit) (_SFR_BYTE(sfr) &= ~_BV(bit))
#define sbi(sfr, bit) (_SFR_BYTE(sfr) |= _BV(bit))

DAC8554 aout(53);

const int NOUT = 32;                                                                                                                                  // Number of Digital Outputs
const int NIN = 8;                                                                                                                                    // Number of Digital Inputs
const int NGPIO = 4;                                                                                                                                  // Number of general purpose Digital Outputs/Digital Inputs/Analog Inputs

int inputs[NIN] = {6,7,8,9,5,4,3,2};                                                                                                                  // Digital Input addresses
bool input_vals[NIN] = {LOW,LOW,LOW,LOW,LOW,LOW,LOW,LOW};                                                                                             // Digital Input values
int outputs[NOUT] = {10,11,12,13,22,23,24,25,26,27,28,29,30,31,32,33,34,35,36,37,38,39,40,41,42,43,44,45,46,47,48,49};                                // Digital Output addresses
bool output_vals[NOUT] = {LOW,LOW,LOW,LOW,LOW,LOW,LOW,LOW,LOW,LOW,LOW,LOW,LOW,LOW,LOW,LOW,LOW,LOW,LOW,LOW,LOW,LOW,LOW,LOW,LOW,LOW,LOW,LOW,LOW,LOW};   // Digital Output values
int gpio_map[NGPIO] = {A0,A1,A2,A3};                                                                                                                  // GPIO address (index) linked to pin name
int gpio_mode[NGPIO] = {0,0,0,0};                                                                                                                     // Current mode for GPIO pin (0=None, 1=Digital Output, 2=Digital Input, 3=Analog Input)
unsigned short gpio_vals[NGPIO] = {LOW,LOW,LOW,LOW};                                                                                                  // GPIO values
unsigned long last_read[NGPIO] = {0,0,0,0};
byte input_buffer[64] = {};
unsigned long period = 1000;

union DigitalOut
{
  byte data;
  struct
  {
    byte command: 3;          // 0
    byte address: 5;          // 0-31
  } parts;
};

union DigitalIn
{
  byte data;
  struct
  {
    byte command: 3;          // 0
    byte address: 3;          // 0-7
    byte rem: 2;
  } parts;
};

union AnalogOut
{
  byte data[3];
  struct
  {
    byte command: 3;          // 1
    byte address: 2;          // 0-3
    unsigned short value: 16;            // 0-65535
    byte rem: 3;
  } parts;
};

union AnalogIn
{
  byte data[2];
  struct
  {
    byte command: 3;          // 1
    byte address: 2;          // 0-3
    unsigned short value: 10;            // 0-1023
    byte rem: 1;
  } parts;
};

union GPIOOut
{
  byte data;
  struct
  {
    byte command: 3;          // 2
    byte address: 2;          // 0-3
    byte rem: 3;
  } parts;
};

union GPIOIn
{
  byte data;
  struct
  {
    byte command: 3;          // 2
    byte address: 2;          // 0-3
    byte rem: 3;
  } parts;
};

union RegisterGPIO
{
  byte data;
  struct
  {
    byte command: 3;          // 3
    byte address: 2;          // 0-3
    byte type: 2;             // 0-3
    byte rem: 1;
  } parts;
};

union Reset
{
  byte data;
  struct
  {
    byte command: 3;          // 4
    byte rem: 5;
  } parts;
};

union AInParams
{
  byte data;
  struct
  {
    byte command: 3;          // 5
    byte fs: 2;               // 0-3
    byte ref: 1;              // 0-1
    byte rem: 2;
  } parts;
};

void setup() {
  sbi(ADCSRA, ADPS2);
  cbi(ADCSRA, ADPS1);
  cbi(ADCSRA, ADPS0);
  Serial.begin(1000000);
  do
  { Serial.read();
  } while (Serial.available() > 0);
  pinModeFast(LED_BUILTIN, OUTPUT);
  // Initialize all Digital Input pins
  for (int i=0; i<NIN; i++) {
    pinModeFast(inputs[i], INPUT);
  }
  // Initialize all Digital Output pins
  for (int i=0; i<NOUT; i++) {
    pinModeFast(outputs[i], OUTPUT);
  }
  // Initialize all GPIO pins
  for (int i=0; i<NGPIO; i++) {
    pinModeFast(gpio_map[i], INPUT);
  }
  aout.begin();
  for (int i=0; i<4; i++) {
    aout.setValue(i, 0);
  }
}

byte cur_command[3] = {};
short cind = 0;

void loop() {
  // If a Serial command has been received
  int avail = Serial.available();
  if (avail > 0){
    //digitalWrite(LED_BUILTIN, HIGH);
    Serial.readBytes(input_buffer, avail);
    for (int i = 0; i < avail; i++) {
      // Read one byte from the command
      cur_command[cind] = input_buffer[i];
      cind++;
      // Extract the command portion of the byte
      int command = cur_command[0] & 0x7;
      switch (command) {
        case 0: { // DigitalOutput
          // Extract the address
          int address = (cur_command[0] >> 3) & 0x1F;
          // Invert the value
          output_vals[address] = !output_vals[address];
          digitalWriteFast(outputs[address], output_vals[address]);
          cind = 0;
          break;
        }
        case 1: { // AnalogOut
          if (cind == 3) {
            union AnalogOut output;
            for(int j = 0; j <= 2; j++)
            {
              output.data[j] = cur_command[j];
            }
            aout.setValue(output.parts.address, output.parts.value);
            cind = 0;
          }
          break;
        }
        case 2: { // GPIOOut
          // Extract the address
          int address = (cur_command[0] >> 3) & 0x3;
          // Invert the value
          gpio_vals[address] = !gpio_vals[address];
          digitalWriteFast(gpio_map[address], gpio_vals[address]);
          cind = 3;
          break;
        }
        case 3: { // RegisterGPIO
          // Extract the address
          int address = (cur_command[0] >> 3) & 0x3;
          // Extract the type
          int type = (cur_command[0] >> 5) & 0x3;
          // Reset the stored values
          if (gpio_mode[address] == 1) {
            digitalWriteFast(gpio_map[address], LOW);
          }
          gpio_mode[address] = type;
          gpio_vals[address] = LOW;
          switch (type) {
            case 0: { // None
              pinModeFast(gpio_map[address], INPUT);
              break;
            }
            case 1: { // GPIOOut
              pinModeFast(gpio_map[address], OUTPUT);
              break;
            }
            case 2: { // GPIOIn
              pinModeFast(gpio_map[address], INPUT);
              break;
            }
            case 3: { // AnalogInput
              pinModeFast(gpio_map[address], INPUT);
              break;
            }
          }
          cind = 0;
          break;
        }
        case 4: { // Reset
          // Reset all Digital Outputs
          for (int j=0; j<NOUT; j++) {
            digitalWriteFast(outputs[j], LOW);
          }
          // Reset all Digital Inputs
          for (int j=0; j<NIN; j++) {
            input_vals[j] = LOW;
          }
          // Reset all GPIO pins
          for (int j=0; j<NGPIO; j++) {
            gpio_mode[j] = 0;
            gpio_vals[j] = LOW;
            pinModeFast(gpio_map[j], INPUT);
          }
          for (int j=0; j<4; j++) {
            aout.setValue(j, 0);
          }
          cind = 0;
          break;
        }
        case 5: { // AInParams
          // Extract the sampling rate
          int fs_type = (cur_command[0] >> 3) & 0x3;
          switch (fs_type) {
            case 0:
              period = 1000000;
              break;
            case 1:
              period = 100000;
              break;
            case 2:
              period = 10000;
              break;
            default:
              period = 1000;
              break;
          }
          // Extract the ref type
          int type = (cur_command[0] >> 4) & 0x1;
          if (type == 0) 
            analogReference(DEFAULT);
          else
            analogReference(INTERNAL2V56);
          cind = 0;
          break;
        }
        default: {
          cind = 0;
          break;
        }
      }
    }
  }
  // Check if any Digital Inputs have changed
  for (int i = 0; i < NIN; i++) {
    int temp = digitalReadFast(inputs[i]);
    if (temp != input_vals[i]) {
      input_vals[i] = temp;
      union DigitalIn input;
      input.parts.command = 0;
      input.parts.address = i;
      input.parts.rem = 0;
      Serial.write(input.data);
    }
  }
  // Read GPIO pins if set to an input mode
  unsigned long ct = micros();
  for (int i = 0; i < 4; i++) {
    switch (gpio_mode[i]) {
      case 0:
      case 1:
        break;
      case 2: { // GPIOIn
        // Check if value has changed
        int temp = digitalReadFast(gpio_map[i]);
        if (temp != gpio_vals[i]) {
          gpio_vals[i] = temp;
          union GPIOIn input;
          input.parts.command = 2;
          input.parts.address = i;
          input.parts.rem = 0;
          Serial.write(input.data);
        }
        break;
      }
      case 3: { // AnalogIn
        // Write the current value
        if (ct - last_read[i] > period) {
          gpio_vals[i] = analogRead(gpio_map[i]);
          union AnalogIn input;
          input.parts.command = 1;
          input.parts.address = i;
          input.parts.value = gpio_vals[i];
          input.parts.rem = 0;
          Serial.write(input.data, 2);
          last_read[i] = ct;
        }
        break;
      }
    }
  }
}
