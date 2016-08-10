var version = require('./package.json').version;

const babelSettings = {
  plugins: [
    'transform-flow-strip-types',
    'add-module-exports',
    'transform-regenerator',
    'transform-decorators-legacy'
  ],
  presets: [ 'es2015', 'react', 'stage-1' ]
};


module.exports = [
    {
      entry: './src/index.js',
      output: {
          filename: 'index.js',
          path: '../timbr/static',
          libraryTarget: 'amd'
      },
      module : {
        loaders : [
          {
            test: /\.js?$/,
            exclude: /(node_modules|bower_components)/,
            loaders: [`babel?${JSON.stringify( babelSettings )}`]
          },
          { 
            test: /\.css$/, loader: "style-loader!css-loader" 
          },
          {
            test: /\.less$/, loader: "style!css!less"
          }
        ]
      }
    },
    {
      entry: './src/components/index.js',
      output: {
          filename: 'components.js',
          path: '../timbr/static',
          libraryTarget: 'amd'
      },
      module : {
        loaders : [
          {
            test: /\.js?$/,
            exclude: /(node_modules|bower_components)/,
            loaders: [`babel?${JSON.stringify( babelSettings )}`]
          }
        ]
      }
    }
];
